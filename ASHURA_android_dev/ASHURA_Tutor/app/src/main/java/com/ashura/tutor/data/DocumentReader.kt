package com.ashura.tutor.data

import android.content.ContentResolver
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.OpenableColumns
import com.ashura.tutor.domain.library.ImportCheck
import com.ashura.tutor.domain.library.OoxmlExtractor
import com.ashura.tutor.domain.library.TextChunker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import kotlin.math.max
import kotlin.math.min

sealed interface ReadResult {
    data class Document(
        val title: String,
        val text: String,
        val mimeType: String,
        /** True when at least one page or image was recognised by OCR rather than embedded text. */
        val usedOcr: Boolean = false,
        /** Page count for PDFs, null for other formats. */
        val pages: Int? = null
    ) : ReadResult

    data class Failure(val message: String) : ReadResult
}

/**
 * Reads a user-picked note via the Storage Access Framework (no storage permission needed).
 *
 * Text/Markdown is decoded strictly as UTF-8; DOCX/XLSX/PPTX are unpacked in memory with hard
 * expansion caps. PDFs and images are streamed to a cache file with a per-format cap so a large
 * document never sits in memory as one byte array. Text PDFs use embedded text; blank/scanned pages
 * are OCR'd with bundled ML Kit recognisers and labelled as OCR in the stored text. All work runs
 * on Dispatchers.IO.
 */
class DocumentReader(
    private val resolver: ContentResolver,
    private val cacheDir: File
) {

    init {
        cacheDir.mkdirs()
    }

    suspend fun read(uri: Uri, language: String = "en"): ReadResult = withContext(Dispatchers.IO) {
        val ocr = DocumentOcr(language)
        try {
            readInternal(uri, ocr)
        } finally {
            ocr.close()
        }
    }

    private suspend fun readInternal(uri: Uri, ocr: DocumentOcr): ReadResult {
        val meta = try {
            queryMetadata(uri)
        } catch (e: SecurityException) {
            return ReadResult.Failure("Permission to read this file was denied.")
        }
        val (name, size) = meta
        val mime = resolver.getType(uri)
        val kind = when (val check = TextChunker.check(mime, name, size)) {
            is ImportCheck.Rejected -> return ReadResult.Failure(check.reason)
            ImportCheck.Ok -> TextChunker.detectKind(mime, name)
                ?: return ReadResult.Failure("This file type is not supported.")
        }

        return try {
            when (kind) {
                TextChunker.Kind.TEXT -> readText(uri, name, kind)
                TextChunker.Kind.DOCX, TextChunker.Kind.XLSX, TextChunker.Kind.PPTX ->
                    readOoxml(uri, name, kind)
                TextChunker.Kind.PDF -> readPdf(uri, name, ocr)
                TextChunker.Kind.IMAGE -> readImage(uri, name, ocr)
            }
        } catch (e: TooLargeException) {
            ReadResult.Failure(e.message ?: "This file is too large to import.")
        } catch (e: SecurityException) {
            ReadResult.Failure("Permission to read this file was denied.")
        } catch (e: IOException) {
            ReadResult.Failure("Could not read the file: ${e.message ?: "I/O error"}")
        }
    }

    // --------------------------------------------------------------- formats

    private fun readText(uri: Uri, name: String?, kind: TextChunker.Kind): ReadResult {
        val bytes = readBytes(uri, TextChunker.maxBytesFor(kind))
        val decoded = try {
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString()
        } catch (_: CharacterCodingException) {
            return ReadResult.Failure("This file is not valid UTF-8 text.")
        }
        if (!TextChunker.looksLikeText(decoded.take(4096))) {
            return ReadResult.Failure("This file does not look like text.")
        }
        val text = TextChunker.normalize(decoded)
        if (text.isBlank()) return ReadResult.Failure("File has no readable text.")
        return ReadResult.Document(titleFor(name, "Imported note"), text, TextChunker.mimeFor(kind))
    }

    private fun readOoxml(uri: Uri, name: String?, kind: TextChunker.Kind): ReadResult {
        val bytes = readBytes(uri, TextChunker.maxBytesFor(kind))
        val ooxmlKind = when (kind) {
            TextChunker.Kind.DOCX -> OoxmlExtractor.Kind.DOCX
            TextChunker.Kind.XLSX -> OoxmlExtractor.Kind.XLSX
            TextChunker.Kind.PPTX -> OoxmlExtractor.Kind.PPTX
            else -> error("not an OOXML kind")
        }
        val extracted = when (val result = OoxmlExtractor.extract(ooxmlKind, ByteArrayInputStream(bytes))) {
            is OoxmlExtractor.Result.Failure -> return ReadResult.Failure(result.reason)
            is OoxmlExtractor.Result.Success -> TextChunker.normalize(result.text)
        }
        if (extracted.isBlank()) return ReadResult.Failure("File has no readable text.")
        return ReadResult.Document(titleFor(name, "Imported note"), extracted, TextChunker.mimeFor(kind))
    }

    private suspend fun readPdf(uri: Uri, name: String?, ocr: DocumentOcr): ReadResult {
        val file = copyToCache(uri, "pdf", TextChunker.MAX_PDF_BYTES.toLong())
        try {
            val extracted = when (val result = PdfTextExtractor.extract(file)) {
                is PdfTextExtractor.Result.Failure -> return ReadResult.Failure(result.reason)
                is PdfTextExtractor.Result.Success -> result
            }
            val normalized = extracted.pages.map { it.pageNumber to TextChunker.normalize(it.text) }
            val blankPages = normalized.filter { it.second.isBlank() }.map { it.first }
            val ocrPages = if (blankPages.isEmpty()) {
                emptyMap()
            } else {
                when (val result = PdfPageOcr(ocr).recognize(file, blankPages)) {
                    is PdfPageOcr.Result.Failure -> return ReadResult.Failure(result.reason)
                    is PdfPageOcr.Result.Success -> result.pages.associate { it.pageNumber to TextChunker.normalize(it.text) }
                }
            }
            val byPage = normalized.toMap()
            val text = buildString {
                extracted.pages.forEach { page ->
                    val embedded = byPage[page.pageNumber].orEmpty()
                    val recognised = ocrPages[page.pageNumber].orEmpty()
                    when {
                        embedded.isNotBlank() -> {
                            appendLine("[Page ${page.pageNumber}]")
                            appendLine(embedded)
                            appendLine()
                        }
                        recognised.isNotBlank() -> {
                            appendLine("[Page ${page.pageNumber} · OCR: check against the original scan]")
                            appendLine(recognised)
                            appendLine()
                        }
                        // Only mention skipped pages inside the extracted range; a page may simply be blank.
                        page.pageNumber <= extracted.totalPages -> {
                            appendLine("[Page ${page.pageNumber} · no readable text]")
                            appendLine()
                        }
                    }
                }
                if (extracted.truncated) {
                    appendLine("[Only the first ${extracted.pages.size} of ${extracted.totalPages} pages were read.]")
                }
            }.trim()
            if (text.isBlank()) {
                return ReadResult.Failure(
                    "This PDF has no selectable text and OCR found nothing. It may be a scanned document with no clear print."
                )
            }
            return ReadResult.Document(
                title = titleFor(name, "Imported PDF"),
                text = text,
                mimeType = TextChunker.mimeFor(TextChunker.Kind.PDF),
                usedOcr = ocrPages.isNotEmpty(),
                pages = extracted.totalPages
            )
        } finally {
            file.delete()
        }
    }

    private suspend fun readImage(uri: Uri, name: String?, ocr: DocumentOcr): ReadResult {
        val file = copyToCache(uri, "image", TextChunker.MAX_IMAGE_BYTES.toLong())
        try {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.absolutePath, bounds)
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
                return ReadResult.Failure("This image could not be decoded.")
            }
            val options = BitmapFactory.Options().apply {
                inSampleSize = sampleSize(bounds.outWidth, bounds.outHeight, MAX_IMAGE_DIMENSION)
                inPreferredConfig = android.graphics.Bitmap.Config.ARGB_8888
            }
            val bitmap = BitmapFactory.decodeFile(file.absolutePath, options)
                ?: return ReadResult.Failure("This image could not be decoded.")
            val text = try {
                TextChunker.normalize(ocr.recognize(bitmap).text)
            } finally {
                bitmap.recycle()
            }
            if (text.isBlank()) return ReadResult.Failure("No readable text was found in this image.")
            return ReadResult.Document(
                title = titleFor(name, "Imported image"),
                text = "[Image · OCR: check against the original image]\n$text",
                mimeType = TextChunker.mimeFor(TextChunker.Kind.IMAGE),
                usedOcr = true
            )
        } finally {
            file.delete()
        }
    }

    // ---------------------------------------------------------------- helpers

    private fun queryMetadata(uri: Uri): Pair<String?, Long?> {
        var name: String? = null
        var size: Long? = null
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                name = c.getStringOrNull(OpenableColumns.DISPLAY_NAME)
                size = c.getLongOrNull(OpenableColumns.SIZE)
            }
        }
        return name to size
    }

    /** Reads a small file into memory, enforcing [maxBytes] while streaming rather than trusting metadata. */
    private fun readBytes(uri: Uri, maxBytes: Long): ByteArray {
        val input = resolver.openInputStream(uri) ?: throw IOException("Could not open the file.")
        return input.use {
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(16 * 1024)
            var total = 0L
            while (true) {
                val n = it.read(buffer)
                if (n < 0) break
                total += n
                if (total > maxBytes) throw TooLargeException(maxSizeMessage(maxBytes))
                out.write(buffer, 0, n)
            }
            out.toByteArray()
        }
    }

    /** Streams a large file to a private cache file so PdfBox/PdfRenderer never receive a 25 MB byte array. */
    private fun copyToCache(uri: Uri, prefix: String, maxBytes: Long): File {
        val file = File.createTempFile("ashura-$prefix-", ".bin", cacheDir)
        try {
            val input = resolver.openInputStream(uri) ?: throw IOException("Could not open the file.")
            input.use { source ->
                file.outputStream().buffered().use { sink ->
                    val buffer = ByteArray(64 * 1024)
                    var total = 0L
                    while (true) {
                        val n = source.read(buffer)
                        if (n < 0) break
                        total += n
                        if (total > maxBytes) throw TooLargeException(maxSizeMessage(maxBytes))
                        sink.write(buffer, 0, n)
                    }
                }
            }
            return file
        } catch (e: Throwable) {
            file.delete()
            throw e
        }
    }

    private fun maxSizeMessage(maxBytes: Long): String =
        "File is larger than ${maxBytes / (1024 * 1024)} MB."

    private fun titleFor(name: String?, fallback: String): String =
        (name ?: fallback).substringBeforeLast('.').ifBlank { fallback }.take(200)

    private fun sampleSize(width: Int, height: Int, target: Int): Int {
        var sample = 1
        var longest = max(width, height)
        while (longest / 2 >= target && sample < 8) {
            sample *= 2
            longest /= 2
        }
        return sample
    }

    /** Writes UTF-8 text to a user-chosen document (Storage Access Framework); returns an error message or null on success. */
    suspend fun writeText(uri: Uri, text: String): String? = withContext(Dispatchers.IO) {
        try {
            val out = resolver.openOutputStream(uri, "wt") ?: return@withContext "Could not open the destination file."
            out.use { it.write(text.toByteArray(Charsets.UTF_8)) }
            null
        } catch (e: SecurityException) {
            "Permission to write this file was denied."
        } catch (e: IOException) {
            "Could not write the file: ${e.message ?: "I/O error"}"
        }
    }

    private class TooLargeException(message: String) : Exception(message)

    private fun android.database.Cursor.getStringOrNull(column: String): String? {
        val i = getColumnIndex(column); return if (i >= 0 && !isNull(i)) getString(i) else null
    }

    private fun android.database.Cursor.getLongOrNull(column: String): Long? {
        val i = getColumnIndex(column); return if (i >= 0 && !isNull(i)) getLong(i) else null
    }

    companion object {
        private const val MAX_IMAGE_DIMENSION = 2_048
    }
}
