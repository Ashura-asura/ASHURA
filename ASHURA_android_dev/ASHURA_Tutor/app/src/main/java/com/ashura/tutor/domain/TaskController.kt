package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.PromptBuilder
import kotlin.coroutines.cancellation.CancellationException

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

    private suspend fun fallthrough(request: TutorRequest): TutorResponse {
        if (modelRuntime.isAvailable) {
            // One bounded model call; no self-reflection loop (spec §5.4). Evidence is trimmed and sanitised.
            val bounded = request.copy(
                retrievedContext = PromptBuilder.trimContext(request.retrievedContext, limits.maxContextCharacters / 2)
            )
            try {
                val generated = modelRuntime.generate(bounded, limits)
                return generated.copy(
                    mode = ResponseMode.LOCAL_MODEL,
                    citations = generated.citations.ifEmpty { citationsFor(bounded) },
                    limitation = generated.limitation
                        ?: "Model-generated explanation; not independently verified."
                )
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                return offlineScaffold(request, "The local model failed (${e.message ?: "unknown error"}); showing a study scaffold instead.")
            }
        }
        return offlineScaffold(request, "This is a study scaffold, not a generated expert explanation.")
    }

    private fun citationsFor(request: TutorRequest): List<String> =
        request.retrievedContext.mapIndexed { i, c -> "[${i + 1}] ${c.sourceLabel}" }

    private fun offlineScaffold(request: TutorRequest, limitation: String): TutorResponse {
        val passages = request.retrievedContext
        if (passages.isNotEmpty()) {
            // Extractive answer: show the learner's own notes, clearly labelled. No generated claims.
            return TutorResponse(
                answer = buildString {
                    appendLine("I found these passages in your notes that may help with: ${request.question}")
                    appendLine()
                    passages.forEachIndexed { i, p ->
                        appendLine("[${i + 1}] ${p.sourceLabel}")
                        appendLine(p.text)
                        appendLine()
                    }
                    append("These are copied from your notes, not explained by a model. Read them, then try to restate the idea in your own words.")
                },
                mode = ResponseMode.OFFLINE_FALLBACK,
                citations = citationsFor(request),
                limitation = "Extractive: passages from your notes, not a generated explanation."
            )
        }
        return TutorResponse(
            answer = buildString {
                if (request.notesSearched) {
                    appendLine("I searched your imported notes and found nothing relevant to this question.")
                    appendLine()
                }
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
            limitation = limitation
        )
    }

    private fun ToolResult.Unhandled.toResponse(): TutorResponse =
        TutorResponse("No tool could handle this request.", ResponseMode.OFFLINE_FALLBACK, limitation = reason)
}
