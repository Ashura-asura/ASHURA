package com.ashura.tutor.domain.runtime

import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.TutorResponse
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Replaceable local-inference boundary (spec §6.2). Cancellation is cooperative: callers cancel
 * the coroutine running [generate]; implementations must stop native work promptly when it is cancelled.
 * Default implementations keep simple fakes and the "no model" runtime trivial.
 */
interface ModelRuntime {
    val isAvailable: Boolean
    suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse

    /**
     * Streaming form of [generate]. Runtimes that cannot stream keep this default, which yields the
     * complete answer as one event; callers therefore only need one code path.
     */
    fun generateStream(request: TutorRequest, limits: GenerationLimits): Flow<TutorStreamEvent> = flow {
        emit(TutorStreamEvent.Complete(generate(request, limits)))
    }

    fun unload()
    /** Loads (or verifies) the model described by [manifest] under [budget]. Default: not supported. */
    suspend fun load(manifest: ModelManifest, budget: ResourceBudget): LoadResult =
        LoadResult.Failed("This runtime cannot load models.")
    fun health(): RuntimeHealth = RuntimeHealth(loaded = isAvailable, detail = null)
}

sealed interface LoadResult {
    data object Loaded : LoadResult
    data class Failed(val reason: String) : LoadResult
}

data class RuntimeHealth(val loaded: Boolean, val detail: String?)

data class GenerationLimits(
    /**
     * Room for a full derivation, not just a one-line answer. A multi-step solution plus a check
     * question can exceed 512 tokens; 1024 lets a 0.6B–1.5B phone model finish without truncation.
     */
    val maxOutputTokens: Int = 1024,
    /**
     * Total wall-clock budget for one answer. At the ~4-8 tokens/s a 1.5B model reaches on a phone,
     * a long derivation can take a few minutes. The UI streams the text and the learner can cancel,
     * so the timeout only bounds a stuck request.
     */
    val timeoutMillis: Long = 180_000,
    val maxContextCharacters: Int = 8_000
) {
    init {
        require(maxOutputTokens in 32..2048)
        require(timeoutMillis in 1_000..300_000)
        require(maxContextCharacters in 1_000..64_000)
    }
}

class UnavailableModelRuntime : ModelRuntime {
    override val isAvailable = false
    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
        error("No local model runtime is configured")
    override fun unload() = Unit
}
