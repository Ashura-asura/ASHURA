package com.ashura.tutor.domain.runtime

/**
 * Pinned model artifacts the app knows how to verify (spec §6.3). Sizes and SHA-256 values come
 * from the Hugging Face LFS metadata of the exact revision named in each manifest. Nothing is
 * bundled in the APK: every artifact is downloaded or imported only after an explicit user action.
 *
 * The catalog deliberately stays small. A model is added only after it has a known licence, a
 * reproducible revision, and a memory tier that the runtime can honour.
 */
object ModelCatalog {

    /**
     * Qwen2.5-1.5B-Instruct, dynamic INT8, 4096-token KV cache — the §6.1 starting candidate.
     * Reported peak RSS is ~2.2 GB on CPU, so it is gated to 6 GB+ devices.
     */
    val qwen15b = ModelManifest(
        id = "qwen2.5-1.5b-instruct-q8-ekv4096",
        revision = "2f23bacf8ec78b83dfcd7271c5cb25777b1be5e0",
        artifactSha256 = "c4a9b7289365ab80fe599b844b77ad253eb3c53fb0e5d963d699146a6f01255e",
        tokenizerSha256 = null, // embedded in the .litertlm bundle
        chatTemplate = "qwen2.5-chatml",
        quantization = "dynamic INT8, multi-prefill-seq, ekv4096",
        contextTokens = 4096,
        license = "Apache-2.0",
        minimumTier = RamTier.STANDARD,
        sizeBytes = 1_597_922_856L,
        displayName = "Qwen2.5 1.5B Instruct (Q8)",
        downloadUrl = "https://huggingface.co/litert-community/Qwen2.5-1.5B-Instruct/resolve/" +
            "2f23bacf8ec78b83dfcd7271c5cb25777b1be5e0/" +
            "Qwen2.5-1.5B-Instruct_multi-prefill-seq_q8_ekv4096.litertlm?download=true"
    )

    /**
     * Qwen3-0.6B, dynamic INT4 (block-32) with float activations — the constrained-tier option.
     * External weights are supported by LiteRT-LM 0.19.x. Thinking is disabled so the tutor gets a
     * direct explanation instead of burning the output budget on hidden reasoning.
     */
    val qwen06b = ModelManifest(
        id = "qwen3-0.6b-int4-ekv4096",
        revision = "bd47201734a34f1eba8ed7d28289225b60152e9e",
        artifactSha256 = "bf1aba9ce8d963124407353c6aa4cbf72eba78db21ae133de983eac672ce83e0",
        tokenizerSha256 = null,
        chatTemplate = "qwen3-chatml",
        quantization = "dynamic INT4 (block-32), float KV, ekv4096",
        contextTokens = 4096,
        license = "Apache-2.0",
        minimumTier = RamTier.CONSTRAINED,
        sizeBytes = 343_490_560L,
        displayName = "Qwen3 0.6B (INT4)",
        downloadUrl = "https://huggingface.co/litert-community/Qwen3-0.6B/resolve/" +
            "bd47201734a34f1eba8ed7d28289225b60152e9e/" +
            "Qwen3-0.6B_dynamic_wi4b32_afp32.litertlm?download=true",
        disableThinking = true
    )

    /** Ordered by preference for a typical phone; the UI filters by [ModelManifest.supports]. */
    val entries: List<ModelManifest> = listOf(qwen15b, qwen06b)

    fun byId(id: String): ModelManifest? = entries.firstOrNull { it.id == id }

    /** Best artifact the device can actually hold: the largest model whose tier fits. */
    fun recommendedFor(deviceTier: RamTier): ModelManifest? =
        entries.filter { it.supports(deviceTier) }
            .maxByOrNull { it.minimumTier.rank }
            ?: entries.minByOrNull { it.sizeBytes }
}
