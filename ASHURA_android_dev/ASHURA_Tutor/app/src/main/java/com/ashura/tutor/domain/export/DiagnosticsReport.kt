package com.ashura.tutor.domain.export

/**
 * Shareable runtime counters for spec §16.5 / P1.2. This deliberately contains no learner text:
 * no questions, answers, note titles, file names, prompts or model output. It is safe to send to a
 * developer when reporting performance on a device.
 */
data class DiagnosticsReport(
    val generatedAt: Long,
    val appVersion: String,
    val androidVersion: String,
    val deviceModel: String,
    val deviceManufacturer: String,
    val supportedAbis: String,
    val ramTier: String,
    val lowRamDevice: Boolean,
    val totalRamMb: Long,
    val freeStorageBytes: Long,
    val backend: String?,
    val loadMillis: Long?,
    val firstTokenMillis: Long?,
    val generationMillis: Long?,
    val estimatedTokens: Int?,
    val tokensPerSecond: Double?,
    val heapUsedMb: Long?
) {
    fun toJson(): String {
        val values = linkedMapOf<String, Any?>(
            "generatedAt" to generatedAt,
            "appVersion" to appVersion,
            "androidVersion" to androidVersion,
            "deviceModel" to deviceModel,
            "deviceManufacturer" to deviceManufacturer,
            "supportedAbis" to supportedAbis,
            "ramTier" to ramTier,
            "lowRamDevice" to lowRamDevice,
            "totalRamMb" to totalRamMb,
            "freeStorageBytes" to freeStorageBytes
        )
        if (backend != null) {
            values["backend"] = backend
            values["loadMillis"] = loadMillis
            values["firstTokenMillis"] = firstTokenMillis
            values["generationMillis"] = generationMillis
            values["estimatedTokens"] = estimatedTokens
            values["tokensPerSecond"] = tokensPerSecond
            values["heapUsedMb"] = heapUsedMb
        }
        values["privacy"] = "Runtime counters only. No questions, answers, notes or file names are included."
        return Json.write(values)
    }
}
