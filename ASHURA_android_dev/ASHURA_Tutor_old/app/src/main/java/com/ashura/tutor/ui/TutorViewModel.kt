package com.ashura.tutor.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.LessonPlanner
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.ReviewOutcome
import com.ashura.tutor.domain.ReviewSchedule
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.TutorEngine
import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.data.LearningStateEntity
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TutorUiState(
    val question: String = "", val answer: String? = null,
    val isBusy: Boolean = false, val error: String? = null
)

class TutorViewModel(
    private val repository: TutorRepository,
    private val engine: TutorEngine,
    private val lessonPlanner: LessonPlanner,
    private val spacingScheduler: SpacingScheduler
) : ViewModel() {
    private val _state = MutableStateFlow(TutorUiState())
    val state: StateFlow<TutorUiState> = _state.asStateFlow()

    private val _lesson = MutableStateFlow<Lesson?>(null)
    val lesson: StateFlow<Lesson?> = _lesson.asStateFlow()

    fun updateQuestion(value: String) = _state.update { it.copy(question = value, error = null) }

    fun ask() {
        val question = _state.value.question.trim()
        if (question.isEmpty() || _state.value.isBusy) return
        _state.update { it.copy(isBusy = true, answer = null, error = null) }
        viewModelScope.launch {
            try {
                val id = repository.createConversation("Study question")
                repository.appendMessage(id, "user", question)
                val result = engine.answer(TutorRequest(question))
                repository.appendMessage(id, "assistant", result.answer, result.mode.name)
                _state.update { it.copy(answer = result.answer, isBusy = false) }
            } catch (timeout: TimeoutCancellationException) {
                _state.update {
                    it.copy(isBusy = false, error = "This request took too long. Try a shorter question.")
                }
            } catch (cancelled: CancellationException) {
                _state.update { it.copy(isBusy = false) }
                throw cancelled
            } catch (failure: Exception) {
                _state.update { it.copy(isBusy = false, error = failure.message ?: "Something went wrong.") }
            }
        }
    }

    fun startLesson(subject: String, topic: String, level: LearnerLevel = LearnerLevel.SCHOOL) {
        _lesson.value = lessonPlanner.plan(subject, topic, level)
    }

    fun clearLesson() = _lesson.value = null

    /**
     * Record a practice attempt, update mastery via the spacing scheduler, and
     * persist the resulting learning state (spec §7.5, §9.4).
     */
    fun recordPractice(
        conceptId: String,
        outcome: ReviewOutcome,
        currentMastery: Double,
        currentIntervalDays: Int
    ): ReviewSchedule {
        val schedule = spacingScheduler.schedule(currentMastery, currentIntervalDays, outcome)
        viewModelScope.launch {
            repository.upsertLearningState(
                conceptId,
                schedule.masteryEstimate,
                if (outcome == ReviewOutcome.INCORRECT) 0.5 else 0.8,
                schedule.nextReviewAt
            )
            repository.recordStudyEvent(conceptId, "practice_$outcome", if (outcome == ReviewOutcome.INCORRECT) 0.0 else 1.0)
        }
        return schedule
    }
}

class TutorViewModelFactory(
    private val repository: TutorRepository,
    private val engine: TutorEngine,
    private val lessonPlanner: LessonPlanner,
    private val spacingScheduler: SpacingScheduler
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(TutorViewModel::class.java))
        return TutorViewModel(repository, engine, lessonPlanner, spacingScheduler) as T
    }
}
