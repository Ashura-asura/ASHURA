package com.ashura.tutor.data

import android.graphics.Bitmap
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.devanagari.DevanagariTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * On-device OCR for scanned pages and images (spec Phase 7). ML Kit's bundled recognisers run without
 * Play Services, an account or a network call. Recognisers are created per import and closed afterwards
 * so no model is kept resident between documents.
 *
 * OCR output is untrusted evidence like any other imported text, and is labelled in the stored document
 * so learners can see that it was machine-recognised.
 */
class DocumentOcr(private val language: String) {

    enum class Script { LATIN, DEVANAGARI }

    data class Result(val text: String, val script: Script)

    private var latinRecognizer: TextRecognizer? = null
    private var devanagariRecognizer: TextRecognizer? = null

    private fun latin(): TextRecognizer =
        latinRecognizer ?: TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            .also { latinRecognizer = it }

    private fun devanagari(): TextRecognizer =
        devanagariRecognizer ?: TextRecognition.getClient(DevanagariTextRecognizerOptions.Builder().build())
            .also { devanagariRecognizer = it }

    /** Nepali is the only Devanagari UI language; everything else uses the Latin recogniser. */
    fun preferredScript(): Script = if (language.lowercase() == "ne") Script.DEVANAGARI else Script.LATIN

    /**
     * Recognises [bitmap] with the preferred script. When [autoRotate] is set and the first pass finds
     * almost nothing, the other three quarter-turns are tried and the richest result wins: phone photos
     * of textbook pages are frequently sideways and ML Kit does not detect that on its own.
     */
    suspend fun recognize(
        bitmap: Bitmap,
        script: Script = preferredScript(),
        autoRotate: Boolean = true
    ): Result {
        val primary = recognizerFor(script)
        var bestText = primary.awaitText(bitmap, 0).trim()
        if (autoRotate && bestText.length < ROTATION_MIN_CHARS) {
            for (rotation in ROTATIONS) {
                val candidate = primary.awaitText(bitmap, rotation).trim()
                if (candidate.length > bestText.length) bestText = candidate
            }
        }
        if (bestText.isNotEmpty() || script != Script.DEVANAGARI) return Result(bestText, script)
        // A Devanagari document may still contain Latin names/terms; try the other recogniser once.
        val fallback = latin().awaitText(bitmap, 0).trim()
        return Result(fallback, Script.LATIN)
    }

    fun close() {
        runCatching { latinRecognizer?.close() }
        runCatching { devanagariRecognizer?.close() }
        latinRecognizer = null
        devanagariRecognizer = null
    }

    private fun recognizerFor(script: Script): TextRecognizer =
        if (script == Script.DEVANAGARI) devanagari() else latin()

    private suspend fun TextRecognizer.awaitText(bitmap: Bitmap, rotationDegrees: Int): String {
        val image = InputImage.fromBitmap(bitmap, rotationDegrees)
        return process(image).await().text
    }

    private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
        addOnSuccessListener { value -> if (continuation.isActive) continuation.resume(value) }
        addOnFailureListener { error -> if (continuation.isActive) continuation.resumeWithException(error) }
        addOnCanceledListener { if (continuation.isActive) continuation.cancel() }
    }

    private companion object {
        const val ROTATION_MIN_CHARS = 12
        val ROTATIONS = intArrayOf(90, 180, 270)
    }
}
