package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
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
}
