package com.ashura.tutor.domain.runtime

/** Memory tiers from spec §16.1. Budgets must still be measured on physical devices. */
enum class RamTier(val label: String) {
    CONSTRAINED("4 GB"), STANDARD("6 GB"), ENHANCED("8 GB+");

    companion object {
        /** Maps total device RAM (bytes) to a tier. Advertised RAM is larger than usable RAM, so thresholds are lenient. */
        fun fromTotalBytes(totalBytes: Long): RamTier {
            val gib = totalBytes / (1024.0 * 1024.0 * 1024.0)
            return when { gib >= 7.0 -> ENHANCED; gib >= 5.0 -> STANDARD; else -> CONSTRAINED }
        }
    }
}

/** Versioned, integrity-checked description of a model artifact (spec §6.3). */
data class ModelManifest(
    val id: String,
    val revision: String,
    val artifactSha256: String,
    val tokenizerSha256: String,
    val chatTemplate: String,
    val quantization: String,
    val contextTokens: Int,
    val license: String,
    val minimumTier: RamTier
) {
    /** Returns human-readable problems; empty means structurally valid. Never trusts the advertised max context. */
    fun problems(): List<String> = buildList {
        val hex = Regex("^[0-9a-f]{64}$")
        if (id.isBlank()) add("id is blank")
        if (revision.isBlank()) add("revision must pin an exact revision")
        if (!hex.matches(artifactSha256)) add("artifactSha256 must be 64 lowercase hex characters")
        if (!hex.matches(tokenizerSha256)) add("tokenizerSha256 must be 64 lowercase hex characters")
        if (license.isBlank()) add("license is blank")
        if (contextTokens !in 512..32_768) add("contextTokens outside 512..32768")
    }
}

/** Per-task ceilings (spec §5.3). */
data class ResourceBudget(val maxContextTokens: Int, val maxOutputTokens: Int, val timeoutMillis: Long)

data class DeviceState(
    val ramTier: RamTier,
    val lowMemory: Boolean = false,
    val criticalThermal: Boolean = false,
    val lowStorage: Boolean = false
)

data class WorkPolicy(
    val maxLoadedModels: Int,
    val contextTokens: Int,
    val serialHeavyTasks: Boolean,
    val pauseEmbeddings: Boolean,
    val pauseBulkOcr: Boolean,
    val pauseIndexing: Boolean,
    val allowOneForegroundTask: Boolean = true
)

/** Resource policy (spec §16.3). Pure function so it is unit-testable without a device. */
object ResourcePolicy {
    fun choose(state: DeviceState): WorkPolicy {
        val pressure = state.lowMemory || state.criticalThermal || state.lowStorage
        val ctx = when (state.ramTier) { RamTier.CONSTRAINED -> 1024; RamTier.STANDARD -> 2048; RamTier.ENHANCED -> 4096 }
        return WorkPolicy(
            maxLoadedModels = 1, // never two models at once on any tier at launch (spec §6.1)
            contextTokens = if (pressure) minOf(ctx, 1024) else ctx,
            serialHeavyTasks = state.ramTier == RamTier.CONSTRAINED || pressure,
            pauseEmbeddings = pressure || state.ramTier == RamTier.CONSTRAINED,
            pauseBulkOcr = pressure,
            pauseIndexing = pressure
        )
    }

    fun budgetFor(policy: WorkPolicy, limits: GenerationLimits = GenerationLimits()): ResourceBudget =
        ResourceBudget(policy.contextTokens, limits.maxOutputTokens, limits.timeoutMillis)
}
