package com.ashura.tutor.domain

/**
 * Honest-confidence label shown under every tutor answer (spec §12). It is derived only from facts the app
 * really knows: how the answer was produced and whether notes were retrieved. It never claims that each
 * statement was checked against the sources, because the app does not do claim-level verification yet.
 */
enum class ConfidenceLabel {
    /** Computed by the exact calculator / unit tools, not by the language model. */
    VERIFIED_BY_CALCULATION,

    /** Built from, or written with, passages retrieved from the learner's own material. Not claim-checked. */
    SUPPORTED_BY_SOURCE,

    /** Written by the local model with no retrieved material behind it. */
    MODEL_ONLY,

    /** No model answer and no matching material: only a generic study scaffold. */
    INSUFFICIENT_EVIDENCE;

    companion object {
        fun forAnswer(mode: ResponseMode?, citations: List<String>): ConfidenceLabel? {
            if (mode == null) return null
            val hasSources = citations.isNotEmpty()
            return when (mode) {
                ResponseMode.DETERMINISTIC -> VERIFIED_BY_CALCULATION
                ResponseMode.LOCAL_MODEL -> if (hasSources) SUPPORTED_BY_SOURCE else MODEL_ONLY
                ResponseMode.OFFLINE_FALLBACK -> if (hasSources) SUPPORTED_BY_SOURCE else INSUFFICIENT_EVIDENCE
            }
        }
    }
}
