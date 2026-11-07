package com.ashura.tutor.ui

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ashura.tutor.application.PracticeService
import com.ashura.tutor.data.ChunkHit
import com.ashura.tutor.data.DocumentReader
import com.ashura.tutor.data.LibraryItemEntity
import com.ashura.tutor.data.ReadResult
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.ReviewOutcome
import com.ashura.tutor.domain.ReviewSchedule
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.assessment.AnswerCheck
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.library.ClozeGenerator
import com.ashura.tutor.domain.library.GroundingPolicy
import com.ashura.tutor.domain.library.PassageRef
import com.ashura.tutor.domain.curriculum.CurriculumPack
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TutorUiState(
    val question: String = "", val answer: String? = null, val limitation: String? = null,
    val citations: List<String> = emptyList(),
    val isBusy: Boolean = false, val error: String? = null
)

data class TopicSummary(val id: String, val title: String, val subject: String, val prerequisiteTitles: List<String>)

data class TopicProgress(
    val topicId: String, val title: String, val mastery: Double,
    val confidence: Double, val nextReviewAt: Long, val due: Boolean
)

data class ProgressUiState(
    val topics: List<TopicProgress> = emptyList(),
    val recommendedTopicId: String? = null,
    val recommendedTitle: String? = null,
    val misconceptions: List<String> = emptyList(),
    val dueCount: Int = 0
)

data class PracticeUiState(
    val question: PracticeQuestion? = null,
    val hintsShown: Int = 0,
    val solutionShown: Boolean = false,
    val busy: Boolean = false,
    val check: AnswerCheck? = null,
    val schedule: ReviewSchedule? = null,
    val error: String? = null,
    /** Wrong answers to this question so far; the first lowers mastery, later ones do not, and success after them counts as assisted. */
    val wrongAttempts: Int = 0,
    /** Questions still queued after this one (note quizzes). */
    val remaining: Int = 0
) {
    val finished: Boolean get() = check?.verdict == Verdict.CORRECT || schedule != null && question?.selfAssessed == true
}

data class LibraryUiState(
    val query: String = "",
    val results: List<ChunkHit> = emptyList(),
    val searched: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null
)

class TutorViewModel(
    private val repository: TutorRepository,
    private val engine: TutorEngine,
    private val lessonPlanner: LessonPlanner,
    private val practiceService: PracticeService,
    private val pack: CurriculumPack,
    private val documentReader: DocumentReader
) : ViewModel() {
    private val _state = MutableStateFlow(TutorUiState())
    val state: StateFlow<TutorUiState> = _state.asStateFlow()

    private val _lesson = MutableStateFlow<Lesson?>(null)
    val lesson: StateFlow<Lesson?> = _lesson.asStateFlow()

    private val _practice = MutableStateFlow(PracticeUiState())
    val practice: StateFlow<PracticeUiState> = _practice.asStateFlow()

    val topics: List<TopicSummary> = pack.learningOrder().map { t ->
        TopicSummary(t.id, t.title, t.subject, t.prerequisites.mapNotNull { pack.topic(it)?.title })
    }

    val progress: StateFlow<ProgressUiState> = combine(
        repository.learningStates(), repository.unresolvedMisconceptions()
    ) { states, misconceptions ->
        val now = System.currentTimeMillis()
        val mastery = states.associate { it.conceptId to it.masteryEstimate }
        val next = pack.nextRecommended(mastery)
        val rows = states.mapNotNull { s ->
            pack.topic(s.conceptId)?.let { TopicProgress(s.conceptId, it.title, s.masteryEstimate, s.confidence, s.nextReviewAt, s.nextReviewAt <= now) }
        }
        ProgressUiState(
            topics = rows, recommendedTopicId = next?.id, recommendedTitle = next?.title,
            misconceptions = misconceptions.mapNotNull { m ->
                pack.topic(m.conceptId)?.misconceptions?.firstOrNull { it.tag == m.tag }?.let { "${it.description} (seen ${m.evidenceCount}×)" }
            },
            dueCount = rows.count { it.due }
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProgressUiState(recommendedTopicId = pack.nextRecommended(emptyMap())?.id,
        recommendedTitle = pack.nextRecommended(emptyMap())?.title))

    val libraryItems: StateFlow<List<LibraryItemEntity>> = repository.libraryItems()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _library = MutableStateFlow(LibraryUiState())
    val library: StateFlow<LibraryUiState> = _library.asStateFlow()
    private var searchJob: Job? = null
    private val quizQueue = ArrayDeque<PracticeQuestion>()

    private val _openTutor = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    /** Emits when a flow started elsewhere (e.g. a note quiz) wants the Tutor tab shown. */
    val openTutorTab: SharedFlow<Unit> = _openTutor.asSharedFlow()

    private val _settingsMessage = MutableStateFlow<String?>(null)
    val settingsMessage: StateFlow<String?> = _settingsMessage.asStateFlow()

    fun importDocument(uri: Uri) {
        if (_library.value.busy) return
        _library.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                when (val read = documentReader.read(uri)) {
                    is ReadResult.Failure -> _library.update { it.copy(busy = false, message = read.message) }
                    is ReadResult.Document -> {
                        val result = repository.importText(read.title, read.text, read.mimeType)
                        val note = "Imported \"${read.title}\" as ${result.chunkCount} passages." +
                            if (result.truncated) " The file was very long, so only the first part was indexed." else ""
                        _library.update { it.copy(busy = false, message = note) }
                    }
                }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(busy = false, message = "Import failed: ${e.message ?: "unknown error"}") }
            }
        }
    }

    fun updateLibraryQuery(text: String) {
        _library.update { it.copy(query = text, message = null) }
        searchJob?.cancel()
        if (text.trim().length < 2) { _library.update { it.copy(results = emptyList(), searched = false) }; return }
        searchJob = viewModelScope.launch {
            kotlinx.coroutines.delay(250) // debounce typing
            try {
                val hits = repository.searchPassages(text)
                _library.update { it.copy(results = hits, searched = true) }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(results = emptyList(), searched = true, message = "Search failed: ${e.message ?: "unknown error"}") }
            }
        }
    }

    /** Builds up to five fill-in-the-blank questions from one imported note and opens the first. */
    fun startNoteQuiz(itemId: String, title: String) {
        viewModelScope.launch {
            try {
                val items = ClozeGenerator.generate(repository.chunksForItem(itemId), 5)
                if (items.isEmpty()) {
                    _library.update { it.copy(message = "This note has too few complete sentences with distinctive terms to make questions.") }
                    return@launch
                }
                quizQueue.clear()
                items.forEachIndexed { i, item ->
                    quizQueue.addLast(
                        PracticeQuestion(
                            id = "note:$itemId:q${i + 1}", conceptId = "note:$itemId",
                            prompt = "Fill in the blank (from \"$title\"): ${item.prompt}",
                            expectedAnswer = item.answer, explanation = "From \"$title\", passage ${item.chunkOrdinal + 1}.",
                            hints = listOf(item.hint)
                        )
                    )
                }
                nextQuizQuestion()
                _openTutor.tryEmit(Unit)
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(message = "Could not start the quiz: ${e.message ?: "unknown error"}") }
            }
        }
    }

    fun nextQuizQuestion() {
        val next = quizQueue.removeFirstOrNull() ?: return
        _practice.value = PracticeUiState(question = next, remaining = quizQueue.size)
    }

    /** Saves a complete JSON export to a file the user picked. */
    fun exportData(uri: Uri) {
        _settingsMessage.value = "Exporting…"
        viewModelScope.launch {
            try {
                val error = documentReader.writeText(uri, repository.exportAllJson())
                _settingsMessage.value = error ?: "Export saved. The file is readable text containing your notes and answers; store it somewhere private."
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _settingsMessage.value = "Export failed: ${e.message ?: "unknown error"}"
            }
        }
    }

    fun deleteLibraryItem(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteLibraryItem(id)
                updateLibraryQuery(_library.value.query) // refresh results so deleted passages disappear
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(message = "Could not delete: ${e.message ?: "unknown error"}") }
            }
        }
    }

    private var conversationId: String? = null
    private var askJob: Job? = null

    fun updateQuestion(value: String) = _state.update { it.copy(question = value, error = null) }

    fun ask() {
        val question = _state.value.question.trim()
        if (question.isEmpty() || _state.value.isBusy) return
        _state.update { it.copy(isBusy = true, answer = null, limitation = null, citations = emptyList(), error = null) }
        askJob = viewModelScope.launch {
            try {
                val id = conversationId ?: repository.createConversation("Study session").also { conversationId = it }
                repository.appendMessage(id, "user", question)
                // Retrieval is best-effort: a search failure must never block the answer.
                val grounded = try {
                    GroundingPolicy.select(repository.searchPassagesForQuestion(question).map { PassageRef(it.title, it.ordinal, it.text) })
                } catch (c: CancellationException) {
                    throw c
                } catch (e: Exception) {
                    GroundingPolicy.select(emptyList())
                }
                val result = engine.answer(TutorRequest(question, retrievedContext = grounded.snippets, notesSearched = true))
                repository.appendMessage(id, "assistant", result.answer, result.mode.name)
                _state.update { it.copy(answer = result.answer, limitation = result.limitation, citations = result.citations, isBusy = false) }
            } catch (timeout: TimeoutCancellationException) {
                _state.update { it.copy(isBusy = false, error = "This request took too long. Try a shorter question.") }
            } catch (cancelled: CancellationException) {
                _state.update { it.copy(isBusy = false) }
                throw cancelled
            } catch (failure: Exception) {
                _state.update { it.copy(isBusy = false, error = failure.message ?: "Something went wrong.") }
            }
        }
    }

    /** User-visible cancellation for a running request (spec §3.3). */
    fun cancelAsk() { askJob?.cancel(); _state.update { it.copy(isBusy = false) } }

    fun startTopic(topicId: String) {
        val topic = pack.topic(topicId) ?: return
        _lesson.value = lessonPlanner.plan(topic.subject, topic.title, topic.level)
    }

    fun startLesson(subject: String, topic: String, level: LearnerLevel = LearnerLevel.SCHOOL) {
        _lesson.value = lessonPlanner.plan(subject, topic, level)
    }

    fun clearLesson() { quizQueue.clear(); _lesson.value = null; _practice.value = PracticeUiState() }

    fun openPractice(question: PracticeQuestion) { _practice.value = PracticeUiState(question = question) }
    fun closePractice() { quizQueue.clear(); _practice.value = PracticeUiState() }

    fun revealHint() = _practice.update { p ->
        val max = p.question?.hints?.size ?: 0
        if (p.hintsShown < max) p.copy(hintsShown = p.hintsShown + 1) else p
    }

    fun showSolution() = _practice.update { it.copy(solutionShown = true) }

    fun submitAnswer(answer: String) {
        val p = _practice.value
        val q = p.question ?: return
        if (p.busy || q.selfAssessed) return
        _practice.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                val outcome = practiceService.submit(q, answer, p.hintsShown, p.solutionShown, p.wrongAttempts)
                _practice.update {
                    it.copy(
                        busy = false, check = outcome.check, schedule = outcome.schedule,
                        wrongAttempts = it.wrongAttempts + if (outcome.check.verdict == Verdict.INCORRECT) 1 else 0
                    )
                }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _practice.update { it.copy(busy = false, error = e.message ?: "Could not save this attempt.") }
            }
        }
    }

    fun submitSelfAssessed(outcome: ReviewOutcome) {
        val p = _practice.value
        val q = p.question ?: return
        if (p.busy) return
        _practice.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                val schedule = practiceService.submitSelfAssessed(q, outcome)
                _practice.update { it.copy(busy = false, schedule = schedule) }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _practice.update { it.copy(busy = false, error = e.message ?: "Could not save this attempt.") }
            }
        }
    }

    /** Spec §15.3: erase all conversations, library, progress and attempts. */
    fun deleteAllData(onDone: () -> Unit) {
        viewModelScope.launch {
            try {
                askJob?.cancel(); searchJob?.cancel(); quizQueue.clear() // no in-flight write may target erased rows
                repository.deleteAllData()
                conversationId = null
                _settingsMessage.value = null
                _state.value = TutorUiState()
                _lesson.value = null
                _practice.value = PracticeUiState()
                _library.value = LibraryUiState()
                onDone()
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _state.update { it.copy(error = "Could not delete data: ${e.message}") }
            }
        }
    }
}

class TutorViewModelFactory(
    private val repository: TutorRepository,
    private val engine: TutorEngine,
    private val lessonPlanner: LessonPlanner,
    private val practiceService: PracticeService,
    private val pack: CurriculumPack,
    private val documentReader: DocumentReader
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(TutorViewModel::class.java))
        return TutorViewModel(repository, engine, lessonPlanner, practiceService, pack, documentReader) as T
    }
}
