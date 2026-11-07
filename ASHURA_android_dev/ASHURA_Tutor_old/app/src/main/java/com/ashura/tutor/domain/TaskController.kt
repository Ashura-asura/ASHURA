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
        val handles: (String) -> Boolean        // can this tool own the request?
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
        if (plan.tools.isNotEmpty()) {
            val tool = tools[plan.tools.first()] ?: return ToolResult.Unhandled("missing tool").toResponse()
            val result = tool.execute(request)
            return when (result) {
                is ToolResult.Handled -> TutorResponse(result.answer, result.mode, result.citations)
                is ToolResult.Unhandled -> fallthrough(request)
            }
        }
        return fallthrough(request)
    }

    private fun fallthrough(request: TutorRequest): TutorResponse {
        return if (modelRuntime.isAvailable) {
            // One bounded model call; no self-reflection loop.
            TutorResponse(
                answer = "Local model path not yet wired for this request.",
                mode = ResponseMode.OFFLINE_FALLBACK,
                limitation = "Model runtime integration is pending."
            )
        } else {
            TutorResponse(
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
    }

    private fun ToolResult.Unhandled.toResponse(): TutorResponse =
        TutorResponse("No tool could handle this request.", ResponseMode.OFFLINE_FALLBACK, limitation = reason)
}
