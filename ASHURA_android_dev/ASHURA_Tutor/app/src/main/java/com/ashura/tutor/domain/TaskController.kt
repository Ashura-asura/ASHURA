package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime

/**
 * Task controller: decides which evidence/tools are needed and builds a bounded
 * execution plan. Prefer deterministic routing for obvious tasks; use the local
 * model only to interpret ambiguous natural language (spec §5.2).
 *
 * Tools are registered pluggably. The controller never retries a deterministic
 * failure and never loops on self-reflection (spec §5.4).
 */
class TaskController(
    private val modelRuntime: ModelRuntime,
    private val tools: Map<String, Tool>,
    private val limits: GenerationLimits = GenerationLimits()
) {

    data class Plan(
        val tools: List<String> = emptyList(),
        val modelRole: String = "tutor",
        val verify: List<String> = emptyList(),
        val maxToolCalls: Int = 3,
    )

    sealed interface ToolResult {
        data class Handled(val answer: String, val mode: ResponseMode, val citations: List<String> = emptyList()) : ToolResult
        data class Unhandled(val reason: String) : ToolResult
    }

    interface Tool {
        val name: String
        val handles: (String) -> Boolean
        suspend fun execute(request: TutorRequest): ToolResult
    }

    /** Route a request to a plan: deterministic tool first, then model, then fallback. */
    fun route(request: String): Plan {
        val lower = request.lowercase()
        val chosen = tools.values.firstOrNull { it.handles(lower) }
        return when {
            chosen != null -> Plan(
                tools = listOf(chosen.name),
                modelRole = "explain_tool_result",
                verify = listOf("recompute"),
                maxToolCalls = 1
            )
            modelRuntime.isAvailable -> Plan(
                tools = emptyList(),
                modelRole = "local_model",
                verify = emptyList(),
                maxToolCalls = 0
            )
            else -> Plan(
                tools = emptyList(),
                modelRole = "offline_fallback",
                verify = emptyList(),
                maxToolCalls = 0
            )
        }
    }

    /** Execute the plan: run the selected tool once; never retry deterministic failures. */
    suspend fun execute(plan: Plan, request: TutorRequest): TutorResponse {
        require(plan.tools.size <= plan.maxToolCalls) { "Plan exceeds its tool-call budget." }
        require(request.question.length <= limits.maxContextCharacters) {
            "Question exceeds the configured context-character limit."
        }
        if (plan.tools.isNotEmpty()) {
            val tool = tools[plan.tools.first()]
                ?: return ToolResult.Unhandled("missing tool").toResponse()
            return when (val result = tool.execute(request)) {
                is ToolResult.Handled -> TutorResponse(result.answer, result.mode, result.citations)
                is ToolResult.Unhandled -> fallthrough(request)
            }
        }
        return fallthrough(request)
    }

    /**
     * Keep the newest retrieved snippets within the context budget, then call
     * the configured runtime. This is the actual model-runtime seam; an
     * available runtime must never silently degrade to a placeholder string.
     */
    private suspend fun fallthrough(request: TutorRequest): TutorResponse {
        if (modelRuntime.isAvailable) {
            val boundedRequest = requestWithBoundedContext(request)
            val generated = modelRuntime.generate(boundedRequest, limits)
            return if (generated.answer.isBlank()) {
                TutorResponse(
                    answer = "The local model returned an empty response. Please try again.",
                    mode = ResponseMode.OFFLINE_FALLBACK,
                    limitation = "The configured model runtime produced no answer."
                )
            } else {
                generated.copy(mode = ResponseMode.LOCAL_MODEL)
            }
        }

        return TutorResponse(
            answer = buildString {
                appendLine("Let's work through this carefully.")
                appendLine()
                appendLine("**Your question:** ${request.question}")
                appendLine()
                appendLine("**Study method**")
                appendLine("1. Identify the key concept and define unfamiliar terms.")
                appendLine("2. List what is known and what must be explained.")
                appendLine("3. Break the task into smaller steps and justify each step.")
                appendLine("4. Check the result independently.")
                appendLine()
                append("No local language model is configured, so I won't invent a subject-specific explanation.")
            },
            mode = ResponseMode.OFFLINE_FALLBACK,
            limitation = "This is a study scaffold, not a generated expert explanation."
        )
    }

    private fun requestWithBoundedContext(request: TutorRequest): TutorRequest {
        var remaining = limits.maxContextCharacters - request.question.length
        val newestFirst = request.retrievedContext.asReversed().mapNotNull { snippet ->
            if (remaining <= 0) return@mapNotNull null
            val boundedText = snippet.text.take(remaining)
            remaining -= boundedText.length
            if (boundedText.isBlank()) null else snippet.copy(text = boundedText)
        }
        return request.copy(retrievedContext = newestFirst.asReversed())
    }

    private fun ToolResult.Unhandled.toResponse(): TutorResponse =
        TutorResponse("No tool could handle this request.", ResponseMode.OFFLINE_FALLBACK, limitation = reason)
}
