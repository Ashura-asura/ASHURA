package com.ashura.tutor.data

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.ashura.tutor.domain.library.ImportCheck
import com.ashura.tutor.domain.library.OoxmlExtractor
import com.ashura.tutor.domain.library.TextChunker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction

sealed interface ReadResult {
    data class Document(val title: String, val text: String, val mimeType: String) : ReadResult
    data class Failure(val message: String) : ReadResult
}

/**
 * Reads a user-picked note via the Storage Access Framework (no storage permission needed).
 * Plain text/Markdown is decoded strictly as UTF-8; DOCX/XLSX/PPTX are unpacked in memory with hard
 * expansion caps. Size is enforced while reading, not trusted from metadata. All work runs on Dispatchers.IO.
 */
class DocumentReader(private val resolver: ContentResolver) {

    suspend fun read(uri: Uri): ReadResult = withContext(Dispatchers.IO) {
        try {
            var name: String? = null
            var size: Long? = null
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    name = c.getStringOrNull(OpenableColumns.DISPLAY_NAME)
                    size = c.getLongOrNull(OpenableColumns.SIZE)
                }
            }
            val mime = resolver.getType(uri)
            when (val check = TextChunker.check(mime, name, size)) {
                is ImportCheck.Rejected -> return@withContext ReadResult.Failure(check.reason)
                ImportCheck.Ok -> Unit
            }
            val kind = TextChunker.detectKind(mime, name)
                ?: return@withContext ReadResult.Failure("This file type is not supported.")
            val stream = resolver.openInputStream(uri) ?: return@withContext ReadResult.Failure("Could not open the file.")
            val bytes = stream.use { input ->
                val out = ByteArrayOutputStream()
                val buf = ByteArray(16 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > TextChunker.MAX_BYTES) return@withContext ReadResult.Failure("File is larger than 2 MB.")
                }
                out.toByteArray()
            }

            val text = if (kind == TextChunker.Kind.TEXT) {
                val decoded = try {
                    Charsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(bytes)).toString()
                } catch (_: CharacterCodingException) {
                    return@withContext ReadResult.Failure("This file is not valid UTF-8 text.")
                }
                if (!TextChunker.looksLikeText(decoded.take(4096))) {
                    return@withContext ReadResult.Failure("This file does not look like text.")
                }
                TextChunker.normalize(decoded)
            } else {
                val ooxmlKind = when (kind) {
                    TextChunker.Kind.DOCX -> OoxmlExtractor.Kind.DOCX
                    TextChunker.Kind.XLSX -> OoxmlExtractor.Kind.XLSX
                    TextChunker.Kind.PPTX -> OoxmlExtractor.Kind.PPTX
                    TextChunker.Kind.TEXT -> error("handled above")
                }
                when (val extracted = OoxmlExtractor.extract(ooxmlKind, ByteArrayInputStream(bytes))) {
                    is OoxmlExtractor.Result.Failure -> return@withContext ReadResult.Failure(extracted.reason)
                    is OoxmlExtractor.Result.Success -> TextChunker.normalize(extracted.text)
                }
            }
            if (text.isBlank()) return@withContext ReadResult.Failure("File has no readable text.")
            val title = (name ?: "Imported note").substringBeforeLast('.').ifBlank { "Imported note" }
            ReadResult.Document(title, text, TextChunker.mimeFor(kind))
        } catch (e: SecurityException) {
            ReadResult.Failure("Permission to read this file was denied.")
        } catch (e: java.io.IOException) {
            ReadResult.Failure("Could not read the file: ${e.message ?: "I/O error"}")
        }
    }

    /** Writes UTF-8 text to a user-chosen document (Storage Access Framework); returns an error message or null on success. */
    suspend fun writeText(uri: Uri, text: String): String? = withContext(Dispatchers.IO) {
        try {
            val out = resolver.openOutputStream(uri, "wt") ?: return@withContext "Could not open the destination file."
            out.use { it.write(text.toByteArray(Charsets.UTF_8)) }
            null
        } catch (e: SecurityException) {
            "Permission to write this file was denied."
        } catch (e: java.io.IOException) {
            "Could not write the file: ${e.message ?: "I/O error"}"
        }
    }

    private fun android.database.Cursor.getStringOrNull(column: String): String? {
        val i = getColumnIndex(column); return if (i >= 0 && !isNull(i)) getString(i) else null
    }
    private fun android.database.Cursor.getLongOrNull(column: String): Long? {
        val i = getColumnIndex(column); return if (i >= 0 && !isNull(i)) getLong(i) else null
    }
}
