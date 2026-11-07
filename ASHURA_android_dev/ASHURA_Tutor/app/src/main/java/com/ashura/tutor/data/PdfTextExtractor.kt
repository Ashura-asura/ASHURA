package com.ashura.tutor.data

import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.encryption.InvalidPasswordException
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.io.File
import kotlin.math.min

/**
 * Text extraction from PDFs using PdfBox-Android (spec Phase 7). Only embedded text is read; scanned
 * pages come back blank and the caller may OCR them. The input is already size-capped by
 * [com.ashura.tutor.domain.library.TextChunker], and page count and output are capped here as well so
 * a crafted PDF cannot exhaust memory or CPU.
 */
object PdfTextExtractor {

    const val MAX_PAGES = 400
    const val MAX_CHARS = 3_000_000

    data class PageText(val pageNumber: Int, val text: String)

    sealed interface Result {
        data class Success(
            val pages: List<PageText>,
            val totalPages: Int,
            val truncated: Boolean
        ) : Result

        data class Failure(val reason: String) : Result
    }

    fun extract(file: File, maxPages: Int = MAX_PAGES): Result {
        var document: PDDocument? = null
        return try {
            document = PDDocument.load(file)
            if (document.isEncrypted) {
                return Result.Failure("This PDF is password-protected or encrypted. Remove the password and import it again.")
            }
            val total = document.numberOfPages
            if (total <= 0) return Result.Failure("This PDF has no pages.")
            val last = min(total, maxPages)
            val stripper = PDFTextStripper().apply {
                sortByPosition = true
                // PdfBox-Android 2.0.27 has pageStart/pageEnd, not a pageSeparator property.
                pageStart = "\u000C"
                pageEnd = ""
                startPage = 1
                endPage = last
            }
            val raw = stripper.getText(document)
            var used = 0
            val pages = ArrayList<PageText>(last)
            val separated = raw.split('\u000C')
            val pageTexts = if (separated.firstOrNull()?.isEmpty() == true) separated.drop(1) else separated
            pageTexts.forEachIndexed { index, page ->
                if (index >= last) return@forEachIndexed
                val room = MAX_CHARS - used
                if (room <= 0) return@forEachIndexed
                val text = page.take(room)
                used += text.length
                pages.add(PageText(index + 1, text))
            }
            Result.Success(
                pages = pages,
                totalPages = total,
                truncated = last < total || used >= MAX_CHARS
            )
        } catch (e: InvalidPasswordException) {
            Result.Failure("This PDF is password-protected or encrypted. Remove the password and import it again.")
        } catch (e: OutOfMemoryError) {
            Result.Failure("This PDF is too large to open safely on this device.")
        } catch (e: Exception) {
            Result.Failure("Could not read this PDF: ${e.message ?: "unknown error"}")
        } finally {
            runCatching { document?.close() }
        }
    }
}
