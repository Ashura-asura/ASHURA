package com.ashura.tutor.domain.runtime

import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.TutorResponse

/**
 * llama.cpp model-runtime adapter stub (spec §6.2).
 *
 * This is the integration point for a quantised local model such as
 * Qwen2.5-1.5B-Instruct. It is intentionally unavailable until a model
 * artifact is bundled and benchmarked on a target device (v5 §6.1, §17.1).
 * The adapter keeps the rest of the app decoupled from any one runtime.
 */
class LlamaCppModelRuntime : ModelRuntime {

    override val isAvailable: Boolean = false

    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse {
        error("llama.cpp runtime is not bundled; model integration is pending device benchmarking.")
    }

    override fun unload() = Unit
}
