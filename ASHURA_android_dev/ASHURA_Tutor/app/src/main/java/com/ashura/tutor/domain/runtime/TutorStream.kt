package com.ashura.tutor.domain.runtime

import com.ashura.tutor.domain.TutorResponse

/**
 * Streaming events from a [ModelRuntime] (spec §6.2, §25 step 4). Deterministic runtimes and
 * unavailable runtimes emit a single [Complete]; LiteRT-LM emits [Delta] as tokens arrive.
 */
sealed interface TutorStreamEvent {
    /** Incremental text to append to the visible answer. */
    data class Delta(val text: String) : TutorStreamEvent

    /** The final, sanitised answer. Always the last event on success. */
    data class Complete(val response: TutorResponse) : TutorStreamEvent
}

/**
 * Measured runtime behaviour, shown in Settings diagnostics (spec §16.5). Values are estimates
 * where the engine does not expose exact token counts.
 */
data class RuntimeMetrics(
    val backend: String = "CPU",
    val loadMillis: Long? = null,
    val firstTokenMillis: Long? = null,
    val generationMillis: Long? = null,
    val estimatedTokens: Int = 0,
    val tokensPerSecond: Double? = null,
    val heapUsedMb: Long? = null
)
