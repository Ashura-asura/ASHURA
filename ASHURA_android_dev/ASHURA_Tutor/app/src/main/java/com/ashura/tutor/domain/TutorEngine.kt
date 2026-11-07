package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.TutorStreamEvent
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withTimeout

/**
 * Teaching engine: orchestrates retrieval, deterministic tools and the local
 * model into a single verified answer (spec §7).
 */
class TutorEngine(
    private val modelRuntime: ModelRuntime,
    private val taskController: TaskController,
    private val limits: GenerationLimits = GenerationLimits()
) {

    suspend fun answer(request: TutorRequest): TutorResponse {
        val question = request.question.trim()
        require(question.isNotEmpty()) { "Ask a question first." }

        val plan = taskController.route(question)
        return withTimeout(limits.timeoutMillis) {
            taskController.execute(
                plan,
                request.copy(question = question, retrievedContext = request.retrievedContext)
            )
        }
    }

    /** Streaming tutor answer (spec §25 step 4): deltas while the local model writes, one final response. */
    fun answerStream(request: TutorRequest): Flow<TutorStreamEvent> = flow {
        val question = request.question.trim()
        require(question.isNotEmpty()) { "Ask a question first." }

        val plan = taskController.route(question)
        withTimeout(limits.timeoutMillis) {
            taskController.executeStream(
                plan,
                request.copy(question = question, retrievedContext = request.retrievedContext)
            ).collect { emit(it) }
        }
    }
}
