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

    suspend fun recognize(bitmap: Bitmap, script: Script = preferredScript()): Result {
        val primary = recognizerFor(script)
        val text = primary.awaitText(bitmap).trim()
        if (text.isNotEmpty() || script != Script.DEVANAGARI) return Result(text, script)
        // A Devanagari document may still contain Latin names/terms; try the other recogniser once.
        val fallback = latin().awaitText(bitmap).trim()
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

    private suspend fun TextRecognizer.awaitText(bitmap: Bitmap): String {
        val image = InputImage.fromBitmap(bitmap, 0)
        return process(image).await().text
    }

    private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
        addOnSuccessListener { value -> if (continuation.isActive) continuation.resume(value) }
        addOnFailureListener { error -> if (continuation.isActive) continuation.resumeWithException(error) }
        addOnCanceledListener { if (continuation.isActive) continuation.cancel() }
    }
}
