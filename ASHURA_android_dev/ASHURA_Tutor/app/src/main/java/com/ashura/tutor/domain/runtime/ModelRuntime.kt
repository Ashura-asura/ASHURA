package com.ashura.tutor.domain.runtime

import com.ashura.tutor.domain.TutorRequest
import com.ashura.tutor.domain.TutorResponse

interface ModelRuntime {
    val isAvailable: Boolean
    suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse
    fun unload()
}

data class GenerationLimits(
    val maxOutputTokens: Int = 384,
    val timeoutMillis: Long = 45_000,
    val maxContextCharacters: Int = 12_000
) {
    init {
        require(maxOutputTokens in 32..2048)
        require(timeoutMillis in 1_000..120_000)
        require(maxContextCharacters in 1_000..64_000)
    }
}

class UnavailableModelRuntime : ModelRuntime {
    override val isAvailable = false
    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
        error("No local model runtime is configured")
    override fun unload() = Unit
}
