package com.ashura.tutor.ui

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ashura.tutor.application.PracticeService
import com.ashura.tutor.data.ChunkHit
import com.ashura.tutor.data.ConversationEntity
import com.ashura.tutor.data.DocumentReader
import com.ashura.tutor.data.LibraryItemEntity
import com.ashura.tutor.data.ReadResult
import com.ashura.tutor.data.StudyLibrary
import com.ashura.tutor.data.StudyPackRepository
import com.ashura.tutor.data.StudySet
import com.ashura.tutor.data.StudySubject
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.data.model.ModelManager
import com.ashura.tutor.data.model.ModelState
import com.ashura.tutor.data.profile.LearnerProfile
import com.ashura.tutor.data.profile.LearnerProfileStore
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.ResponseMode
import com.ashura.tutor.domain.ReviewOutcome
import com.ashura.tutor.domain.ReviewSchedule
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.TutorStyle
import com.ashura.tutor.domain.library.PassageRef
import com.ashura.tutor.domain.library.SectionLabel
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.RamTier
import com.ashura.tutor.domain.runtime.RuntimeMetrics
import com.ashura.tutor.domain.runtime.TutorStreamEvent
import com.ashura.tutor.domain.assessment.AnswerCheck
import com.ashura.tutor.domain.assessment.HintLadder
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.library.GroundingPolicy
import com.ashura.tutor.domain.library.QuizBuilder
import com.ashura.tutor.domain.library.QuizKind
import com.ashura.tutor.domain.library.TextChunker
import com.ashura.tutor.domain.curriculum.CurriculumPack
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class TutorUiState(
    val question: String = "", val answer: String? = null, val limitation: String? = null,
    val citations: List<String> = emptyList(),
    val isBusy: Boolean = false, val error: String? = null,
    val mode: ResponseMode? = null,
    /** Full chat transcript for the tutor screen. */
    val messages: List<ChatMessage> = emptyList()
)

enum class ChatRole { USER, ASSISTANT }

data class ChatMessage(
    val id: String,
    val role: ChatRole,
    val text: String,
    val mode: ResponseMode? = null,
    val citations: List<String> = emptyList(),
    val limitation: String? = null,
    val streaming: Boolean = false
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
    private val documentReader: DocumentReader,
    private val modelManager: ModelManager,
    private val learnerProfile: LearnerProfileStore,
    private val studyPacks: StudyPackRepository
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

    /** Null until the first database read, so the Library never flashes a false "not indexed". */
    val chunkCounts: StateFlow<Map<String, Int>?> = repository.chunkCounts()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Past tutor conversations, newest first, for the history list. */
    val conversations: StateFlow<List<ConversationEntity>> = repository.conversations()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    // Local model state is owned by the application-scoped manager so a download or load survives
    // screen recreation and only one engine ever exists.
    val modelState: StateFlow<ModelState> = modelManager.state
    val modelCatalog: List<ModelManifest> = modelManager.catalog
    val deviceTier: RamTier = modelManager.deviceTier

    fun downloadModel(id: String) {
        modelCatalog.firstOrNull { it.id == id }?.let(modelManager::download)
    }

    fun importModel(uri: Uri) = modelManager.importFromUri(uri)

    fun loadModel() = modelManager.loadInstalled()

    fun unloadModel() = modelManager.unload()

    fun deleteModel() = modelManager.deleteInstalled()

    fun cancelModelDownload() = modelManager.cancelDownload()

    fun freeStorageBytes(): Long = modelManager.freeStorageBytes()

    /** Learner-selected level/style/language, persisted locally (spec §1.4). */
    val profile: StateFlow<LearnerProfile> = learnerProfile.profile
    val runtimeMetrics: StateFlow<RuntimeMetrics?> = modelManager.metrics

    fun setLearnerLevel(level: LearnerLevel) = updateProfile { it.copy(level = level) }

    fun setTutorStyle(style: TutorStyle) = updateProfile { it.copy(style = style) }

    fun setResponseLanguage(language: String) = updateProfile {
        it.copy(language = language.takeIf { code -> code in LearnerProfileStore.SUPPORTED_LANGUAGES } ?: "en")
    }

    private fun updateProfile(transform: (LearnerProfile) -> LearnerProfile) =
        learnerProfile.update(transform(learnerProfile.profile.value))

    private val _library = MutableStateFlow(LibraryUiState())
    val library: StateFlow<LibraryUiState> = _library.asStateFlow()
    private var searchJob: Job? = null
    private val quizQueue = ArrayDeque<PracticeQuestion>()

    private val _openTutor = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    /** Emits when a flow started elsewhere (e.g. a note quiz) wants the Tutor tab shown. */
    val openTutorTab: SharedFlow<Unit> = _openTutor.asSharedFlow()

    private val _settingsMessage = MutableStateFlow<String?>(null)
    val settingsMessage: StateFlow<String?> = _settingsMessage.asStateFlow()

    private val _studyLibrary = MutableStateFlow<StudyLibrary?>(null)
    val studyLibrary: StateFlow<StudyLibrary?> = _studyLibrary.asStateFlow()

    init {
        viewModelScope.launch {
            try {
                _studyLibrary.value = withContext(Dispatchers.IO) { studyPacks.loadCatalog() }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update {
                    it.copy(message = "Built-in study sets could not be loaded: ${e.message ?: "unknown error"}")
                }
            }
        }
    }

    /** Adds one bundled, checksum-verified study note to the local library. */
    fun importStudySet(set: StudySet) {
        if (_library.value.busy) return
        _library.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                if (repository.hasLibraryTitle(set.title)) {
                    _library.update { it.copy(busy = false, message = "\"${set.title}\" is already in your library.") }
                    return@launch
                }
                val text = studyPacks.readSet(set)
                val result = repository.importText(set.title, TextChunker.normalize(text), "text/markdown")
                _library.update {
                    it.copy(
                        busy = false,
                        message = "Added \"${set.title}\" as ${result.chunkCount} passages. Open it here and tap Quiz."
                    )
                }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(busy = false, message = "Could not add the study set: ${e.message ?: "unknown error"}") }
            }
        }
    }

    /** Adds every set in a subject, skipping titles the learner already has. */
    fun importStudySubject(subject: StudySubject) {
        if (_library.value.busy) return
        _library.update { it.copy(busy = true, message = "Adding ${subject.name}…") }
        viewModelScope.launch {
            try {
                var added = 0
                var skipped = 0
                for (set in subject.sets) {
                    if (repository.hasLibraryTitle(set.title)) {
                        skipped++
                        continue
                    }
                    val text = studyPacks.readSet(set)
                    repository.importText(set.title, TextChunker.normalize(text), "text/markdown")
                    added++
                }
                val suffix = if (skipped > 0) " ($skipped already in your library)" else ""
                _library.update {
                    it.copy(busy = false, message = "Added $added study sets from ${subject.name}$suffix.")
                }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(busy = false, message = "Could not add ${subject.name}: ${e.message ?: "unknown error"}") }
            }
        }
    }

    fun importDocument(uri: Uri) {
        if (_library.value.busy) return
        _library.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                when (val read = documentReader.read(uri, learnerProfile.profile.value.language)) {
                    is ReadResult.Failure -> _library.update { it.copy(busy = false, message = read.message) }
                    is ReadResult.Document -> {
                        val result = repository.importText(read.title, read.text, read.mimeType)
                        val extras = buildList {
                            read.pages?.let { add("$it pages") }
                            if (read.usedOcr) add("OCR used for scanned content")
                        }
                        val note = "Imported \"${read.title}\" as ${result.chunkCount} passages" +
                            (if (extras.isEmpty()) "." else " (${extras.joinToString(", ")}).") +
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

    /**
     * Builds a mixed test set (recall, definitions and explanations) from one imported document and
     * opens the first question. Works with or without a loaded model because every item is derived
     * from the learner's own text.
     */
    fun startNoteQuiz(itemId: String, title: String) {
        viewModelScope.launch {
            try {
                val items = QuizBuilder.build(repository.chunksForItem(itemId), title, QuizBuilder.DEFAULT_MAX)
                if (items.isEmpty()) {
                    _library.update { it.copy(message = "This note has too few complete sentences with distinctive terms to make questions.") }
                    return@launch
                }
                quizQueue.clear()
                items.forEachIndexed { i, item ->
                    val hints = listOfNotNull(item.hint)
                    quizQueue.addLast(
                        PracticeQuestion(
                            id = "note:$itemId:q${i + 1}", conceptId = "note:$itemId",
                            prompt = item.prompt,
                            expectedAnswer = item.answer,
                            explanation = item.explanation,
                            hints = hints,
                            selfAssessed = item.selfAssessed
                        )
                    )
                }
                val cloze = items.count { it.kind == QuizKind.CLOZE }
                val written = items.count { it.kind != QuizKind.CLOZE }
                _library.update {
                    it.copy(
                        message = "Built ${items.size} questions from \"$title\": " +
                            "$cloze recall and $written explain/define."
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

    /**
     * Saves a learner's corrections to imported text (spec §9.3). OCR output is always shown as
     * editable because a scanned page may misread names and numbers; correcting it re-indexes the
     * passages so later searches, citations and quizzes use the corrected wording.
     */
    fun updateLibraryText(id: String, title: String, text: String) {
        viewModelScope.launch {
            try {
                val chunks = repository.replaceLibraryText(id, text)
                _library.update { it.copy(message = "Saved corrections to \"$title\" as $chunks passages.") }
                updateLibraryQuery(_library.value.query)
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(message = "Could not save this note: ${e.message ?: "unknown error"}") }
            }
        }
    }

    /** Spec §9.4: rebuild passages for an item that has stored text but no searchable chunks. */
    fun reindexLibraryItem(id: String, title: String) {
        viewModelScope.launch {
            try {
                val passages = repository.reindexLibraryItem(id)
                _library.update { it.copy(message = "Re-indexed \"$title\": $passages passages.") }
                updateLibraryQuery(_library.value.query)
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _library.update { it.copy(message = "Could not re-index this note: ${e.message ?: "unknown error"}") }
            }
        }
    }

    private var conversationId: String? = null
    private var askJob: Job? = null

    fun updateQuestion(value: String) = _state.update { it.copy(question = value, error = null) }

    fun ask() {
        val question = _state.value.question.trim()
        if (question.isEmpty() || _state.value.isBusy) return
        val assistantId = "a${System.nanoTime()}"
        _state.update {
            it.copy(
                isBusy = true, answer = "", limitation = null, citations = emptyList(),
                error = null, mode = null, question = "",
                messages = it.messages +
                    ChatMessage("u${System.nanoTime()}", ChatRole.USER, question) +
                    ChatMessage(assistantId, ChatRole.ASSISTANT, "", streaming = true)
            )
        }
        askJob = viewModelScope.launch {
            try {
                val id = conversationId ?: repository.createConversation(question.replace("\n", " ").take(48)).also { conversationId = it }
                repository.appendMessage(id, "user", question)
                // Retrieval is best-effort: a search failure must never block the answer.
                val grounded = try {
                    GroundingPolicy.select(repository.searchPassagesForQuestion(question).map {
                        PassageRef(it.title, it.ordinal, it.text, SectionLabel.forChunk(it.text))
                    })
                } catch (c: CancellationException) {
                    throw c
                } catch (e: Exception) {
                    GroundingPolicy.select(emptyList())
                }
                val profile = learnerProfile.profile.value
                // Socratic guidance must not become an obstacle (spec §1.2C): "just tell me" switches
                // this one answer to direct explanation without changing the saved preference.
                val effectiveStyle = if (
                    profile.style == TutorStyle.SOCRATIC && HintLadder.asksForDirectAnswer(question)
                ) TutorStyle.DIRECT else profile.style
                val request = TutorRequest(
                    question = question,
                    learnerLevel = profile.level,
                    language = profile.language,
                    style = effectiveStyle,
                    retrievedContext = grounded.snippets,
                    notesSearched = true
                )
                val streamed = StringBuilder()
                engine.answerStream(request).collect { event ->
                    when (event) {
                        is TutorStreamEvent.Delta -> {
                            streamed.append(event.text)
                            updateAssistant(assistantId) { it.copy(text = streamed.toString()) }
                            _state.update { it.copy(answer = streamed.toString()) }
                        }
                        is TutorStreamEvent.Complete -> {
                            val result = event.response
                            repository.appendMessage(id, "assistant", result.answer, result.mode.name)
                            updateAssistant(assistantId) {
                                it.copy(
                                    text = result.answer, mode = result.mode,
                                    citations = result.citations, limitation = result.limitation,
                                    streaming = false
                                )
                            }
                            _state.update {
                                it.copy(
                                    answer = result.answer, limitation = result.limitation,
                                    citations = result.citations, isBusy = false, mode = result.mode
                                )
                            }
                        }
                    }
                }
            } catch (timeout: TimeoutCancellationException) {
                failAssistant(assistantId)
                _state.update {
                    it.copy(
                        isBusy = false,
                        error = "The model ran out of time before finishing. Try again, or ask for the " +
                            "derivation one step at a time."
                    )
                }
            } catch (cancelled: CancellationException) {
                finishStopped(assistantId)
                _state.update { it.copy(isBusy = false) }
                throw cancelled
            } catch (failure: Exception) {
                failAssistant(assistantId)
                _state.update { it.copy(isBusy = false, error = failure.message ?: "Something went wrong.") }
            }
        }
    }

    /** User-visible cancellation for a running request (spec §3.3). */
    fun cancelAsk() {
        val streaming = _state.value.messages.filter { it.streaming }.map { it.id }
        askJob?.cancel()
        _state.update { s ->
            s.copy(
                isBusy = false,
                messages = s.messages.map { message ->
                    if (message.id in streaming) message.copy(
                        text = message.text.ifBlank { "Stopped." },
                        streaming = false
                    ) else message
                }
            )
        }
    }

    /** Re-asks the last question: drops the last answer (and its question bubble) and runs the request again. */
    fun regenerate() {
        val s = _state.value
        if (s.isBusy) return
        val lastAssistant = s.messages.lastOrNull()?.takeIf { it.role == ChatRole.ASSISTANT } ?: return
        val lastUser = s.messages.dropLast(1).lastOrNull()?.takeIf { it.role == ChatRole.USER } ?: return
        _state.update { it.copy(messages = it.messages.dropLast(2), question = lastUser.text, error = null) }
        ask()
    }

    /** Re-opens a stored conversation (text only: source citations are not persisted per message). */
    fun openConversation(id: String) {
        viewModelScope.launch {
            try {
                askJob?.cancel(); askJob = null
                val stored = repository.loadConversation(id)
                conversationId = id
                _state.update {
                    it.copy(
                        messages = stored.map { m ->
                            ChatMessage(
                                id = m.id,
                                role = if (m.role == "user") ChatRole.USER else ChatRole.ASSISTANT,
                                text = m.content,
                                // Per-message citations are not persisted, so a reopened model answer
                                // must not claim a confidence label it can no longer support. Only the
                                // deterministic marker is safe to restore.
                                mode = m.source
                                    ?.let { s -> ResponseMode.values().firstOrNull { r -> r.name == s } }
                                    ?.takeIf { it == ResponseMode.DETERMINISTIC }
                            )
                        },
                        question = "", answer = null, limitation = null, citations = emptyList(),
                        isBusy = false, error = null, mode = null
                    )
                }
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _state.update { it.copy(error = "Could not open this chat: ${e.message}") }
            }
        }
    }

    fun deleteConversation(id: String) {
        viewModelScope.launch {
            try {
                if (id == conversationId) newChat()
                repository.deleteConversation(id)
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _state.update { it.copy(error = "Could not delete this chat: ${e.message}") }
            }
        }
    }

    /** Starts a fresh conversation without touching the stored history for the previous one. */
    fun newChat() {
        askJob?.cancel()
        askJob = null
        conversationId = null
        _state.update {
            it.copy(
                messages = emptyList(), question = "", answer = null, limitation = null,
                citations = emptyList(), isBusy = false, error = null, mode = null
            )
        }
    }

    private fun updateAssistant(id: String, transform: (ChatMessage) -> ChatMessage) {
        _state.update { state ->
            state.copy(messages = state.messages.map { if (it.id == id) transform(it) else it })
        }
    }

    private fun finishStopped(id: String) = updateAssistant(id) {
        it.copy(text = it.text.ifBlank { "Stopped." }, streaming = false)
    }

    private fun failAssistant(id: String) = updateAssistant(id) {
        it.copy(
            text = it.text.ifBlank { "I couldn't finish that answer. Check the message below and try again." },
            streaming = false
        )
    }

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

    /** Spec §15.3: erase chat history only; imported notes and learning progress stay. */
    fun clearChatHistory() {
        viewModelScope.launch {
            try {
                askJob?.cancel()
                repository.clearChatHistory()
                conversationId = null
                _state.update {
                    it.copy(
                        messages = emptyList(), question = "", answer = null, limitation = null,
                        citations = emptyList(), isBusy = false, error = null, mode = null
                    )
                }
                _settingsMessage.value = null
            } catch (c: CancellationException) {
                throw c
            } catch (e: Exception) {
                _state.update { it.copy(error = "Could not clear chat history: ${e.message}") }
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
    private val documentReader: DocumentReader,
    private val modelManager: ModelManager,
    private val learnerProfile: LearnerProfileStore,
    private val studyPacks: StudyPackRepository
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(TutorViewModel::class.java))
        return TutorViewModel(
            repository, engine, lessonPlanner, practiceService, pack, documentReader,
            modelManager, learnerProfile, studyPacks
        ) as T
    }
}
