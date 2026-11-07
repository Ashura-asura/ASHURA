package com.ashura.tutor.data

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import kotlin.math.max
import kotlin.math.min

/**
 * Renders scanned PDF pages with Android's [PdfRenderer] and feeds them to [DocumentOcr]. One page is
 * held in memory at a time (spec Phase 7: large documents must not exhaust memory). PDF rendering is
 * bounded to [MAX_OCR_PAGES] pages; the remainder is left clearly marked as not recognised.
 */
class PdfPageOcr(private val ocr: DocumentOcr) {

    data class PageOcr(val pageNumber: Int, val text: String)

    sealed interface Result {
        data class Success(
            val pages: List<PageOcr>,
            val skippedPages: Int,
            val failedPages: Int = 0
        ) : Result
        data class Failure(val reason: String) : Result
    }

    suspend fun recognize(file: File, pageNumbers: List<Int>): Result = withContext(Dispatchers.IO) {
        if (pageNumbers.isEmpty()) return@withContext Result.Success(emptyList(), 0)
        val wanted = pageNumbers.distinct().sorted().take(MAX_OCR_PAGES)
        val skipped = pageNumbers.distinct().size - wanted.size
        var descriptor: ParcelFileDescriptor? = null
        var renderer: PdfRenderer? = null
        try {
            descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
            renderer = PdfRenderer(descriptor)
            val results = ArrayList<PageOcr>(wanted.size)
            var failed = 0
            for (number in wanted) {
                val index = number - 1
                if (index !in 0 until renderer.pageCount) continue
                // One damaged page must not discard the rest of a scanned document.
                try {
                    val bitmap = renderPage(renderer, index)
                    try {
                        val text = ocr.recognize(bitmap).text.trim()
                        if (text.isNotEmpty()) results.add(PageOcr(number, text))
                    } finally {
                        bitmap.recycle()
                    }
                } catch (e: Exception) {
                    failed++
                }
            }
            Result.Success(results, skipped, failed)
        } catch (e: IOException) {
            Result.Failure("Could not read the scanned pages: ${e.message ?: "I/O error"}")
        } catch (e: OutOfMemoryError) {
            Result.Failure("A scanned page is too large to recognise on this device.")
        } catch (e: Exception) {
            Result.Failure("Scanned-page recognition failed: ${e.message ?: "unknown error"}")
        } finally {
            runCatching { renderer?.close() }
            runCatching { descriptor?.close() }
        }
    }

    private fun renderPage(renderer: PdfRenderer, index: Int): Bitmap {
        renderer.openPage(index).use { page ->
            val scale = min(1.6f, MAX_DIMENSION.toFloat() / max(page.width, page.height).coerceAtLeast(1))
            val width = max(1, (page.width * scale).toInt())
            val height = max(1, (page.height * scale).toInt())
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(android.graphics.Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            return bitmap
        }
    }

    companion object {
        const val MAX_OCR_PAGES = 24
        private const val MAX_DIMENSION = 1_800f
    }
}
