package com.ashura.tutor.domain.library

/** A retrievable passage with its position in the normalised source text (provenance, spec §10.1). */
data class TextChunk(val ordinal: Int, val text: String, val startOffset: Int, val endOffset: Int)

sealed interface ImportCheck {
    data object Ok : ImportCheck
    data class Rejected(val reason: String) : ImportCheck
}

/**
 * Pure text-import rules: validation, normalisation and chunking. Android file reading lives elsewhere so
 * this can be unit-tested on a JVM. Imported text is untrusted data; it is only ever stored and retrieved.
 */
object TextChunker {
    const val MAX_BYTES = 2 * 1024 * 1024
    const val MAX_PDF_BYTES = 25 * 1024 * 1024
    const val MAX_IMAGE_BYTES = 15 * 1024 * 1024
    const val MAX_CHUNKS = 2_000
    const val TARGET_CHARS = 900
    const val MAX_CHARS = 1_400
    private val allowedMime = setOf("text/plain", "text/markdown", "text/x-markdown")

    /**
     * Page/slide/sheet labels inserted by the document extractors. A new provenance label starts a new
     * chunk so citations and generated quizzes keep per-page context instead of merging several pages.
     */
    private val provenanceLine = Regex(
        "\\n\\[(?:Page \\d+[^]\\n]{0,80}|Slide \\d+[^]\\n]{0,80}|Sheet: [^]\\n]{1,60}|Image(?: \\d+)?[^]\\n]{0,80})]\\s*\\n"
    )

    /** Import formats supported by the current build. OOXML containers are unpacked in memory. */
    enum class Kind { TEXT, CSV, DOCX, XLSX, PPTX, PDF, IMAGE }

    private val extensionKinds = mapOf(
        "txt" to Kind.TEXT, "md" to Kind.TEXT, "markdown" to Kind.TEXT,
        "csv" to Kind.CSV, "tsv" to Kind.CSV,
        "docx" to Kind.DOCX, "xlsx" to Kind.XLSX, "pptx" to Kind.PPTX,
        "pdf" to Kind.PDF,
        "png" to Kind.IMAGE, "jpg" to Kind.IMAGE, "jpeg" to Kind.IMAGE, "webp" to Kind.IMAGE
    )

    private const val DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    private const val XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    private const val PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    private const val PDF_MIME = "application/pdf"
    private const val IMAGE_MIME = "image/*"

    fun detectKind(mimeType: String?, displayName: String?): Kind? {
        val extension = displayName.orEmpty().lowercase().substringAfterLast('.', "")
        extensionKinds[extension]?.let { return it }
        val mime = mimeType.orEmpty().lowercase()
        return when {
            mime in allowedMime -> Kind.TEXT
            mime == "text/csv" || mime == "text/comma-separated-values" || mime == "text/tab-separated-values" -> Kind.CSV
            mime == DOCX_MIME -> Kind.DOCX
            mime == XLSX_MIME -> Kind.XLSX
            mime == PPTX_MIME -> Kind.PPTX
            mime == PDF_MIME -> Kind.PDF
            mime == "image/png" || mime == "image/jpeg" || mime == "image/webp" -> Kind.IMAGE
            else -> null
        }
    }

    fun mimeFor(kind: Kind): String = when (kind) {
        Kind.TEXT -> "text/plain"
        Kind.CSV -> "text/csv"
        Kind.DOCX -> DOCX_MIME
        Kind.XLSX -> XLSX_MIME
        Kind.PPTX -> PPTX_MIME
        Kind.PDF -> PDF_MIME
        Kind.IMAGE -> IMAGE_MIME
    }

    /** Per-format input cap; PDFs and images are streamed to a temp file rather than held as one byte array. */
    fun maxBytesFor(kind: Kind): Long = when (kind) {
        Kind.PDF -> MAX_PDF_BYTES.toLong()
        Kind.IMAGE -> MAX_IMAGE_BYTES.toLong()
        else -> MAX_BYTES.toLong()
    }

    fun check(mimeType: String?, displayName: String?, sizeBytes: Long?): ImportCheck {
        val name = displayName.orEmpty().lowercase()
        val legacy = listOf(".doc", ".xls", ".ppt").any { name.endsWith(it) }
        if (legacy) {
            return ImportCheck.Rejected("Legacy .doc/.xls/.ppt files are not supported. Save the file as .docx/.xlsx/.pptx first.")
        }
        // Extension wins (providers often report generic MIME types); MIME is the fallback when there is no name.
        val kind = detectKind(mimeType, displayName)
            ?: return ImportCheck.Rejected("Only .txt, .md, .csv, .pdf, .docx, .xlsx, .pptx and image files are supported.")
        val max = maxBytesFor(kind)
        if (sizeBytes != null && sizeBytes > max) return ImportCheck.Rejected("File is larger than ${max / (1024 * 1024)} MB.")
        if (sizeBytes != null && sizeBytes == 0L) return ImportCheck.Rejected("File is empty.")
        if (kind != Kind.TEXT && sizeBytes != null && sizeBytes < 4L) return ImportCheck.Rejected("File is empty.")
        return ImportCheck.Ok
    }

    /**
     * Removes BOM, NUL/control characters, normalises line endings, strips trailing blanks per line and
     * collapses runs of blank lines to one. Strictly linear time: regexes with `[ \t]+\n` were quadratic on
     * long whitespace runs (31 s for 160k spaces), which a crafted or accidental file could exploit.
     */
    fun normalize(raw: String): String {
        val cleaned = StringBuilder(raw.length)
        var i = if (raw.startsWith("\uFEFF")) 1 else 0
        while (i < raw.length) {
            val c = raw[i]
            when {
                c == '\r' -> { cleaned.append('\n'); if (i + 1 < raw.length && raw[i + 1] == '\n') i++ }
                c == '\n' || c == '\t' -> cleaned.append(c)
                c.isISOControl() -> Unit
                else -> cleaned.append(c)
            }
            i++
        }
        val out = StringBuilder(cleaned.length)
        var blankRun = 0
        var first = true
        var start = 0
        val n = cleaned.length
        while (start <= n) {
            var end = cleaned.indexOf("\n", start)
            if (end < 0) end = n
            var e = end
            while (e > start && (cleaned[e - 1] == ' ' || cleaned[e - 1] == '\t')) e--
            if (e == start) {
                blankRun++
            } else {
                if (!first) out.append(if (blankRun > 0) "\n\n" else "\n")
                out.append(cleaned, start, e)
                blankRun = 0
                first = false
            }
            start = end + 1
        }
        return out.toString().trim()
    }

    /** True if the bytes look like text rather than a binary file renamed to .txt. */
    fun looksLikeText(sample: String): Boolean {
        if (sample.isEmpty()) return false
        val bad = sample.count { it == '\u0000' || it == '\uFFFD' }
        return bad.toDouble() / sample.length < 0.01
    }

    /**
     * Splits [normalized] text into chunks of about [TARGET_CHARS], preferring paragraph, then sentence,
     * then whitespace boundaries; never exceeds [MAX_CHARS]. Offsets index into [normalized].
     * Returns at most [MAX_CHUNKS] chunks; [truncated] reports if text remained.
     */
    fun chunk(normalized: String): Chunking {
        val chunks = ArrayList<TextChunk>()
        var pos = 0
        val n = normalized.length
        while (pos < n && chunks.size < MAX_CHUNKS) {
            while (pos < n && normalized[pos].isWhitespace()) pos++
            if (pos >= n) break
            val hardEnd = minOf(n, pos + MAX_CHARS)
            var end = if (hardEnd == n) n else breakPoint(normalized, pos, hardEnd)
            // Keep page/slide/sheet provenance intact: never swallow the next label into this chunk.
            val marker = provenanceLine.find(normalized.substring(pos, end))
            if (marker != null) {
                val cut = pos + marker.range.first
                if (cut > pos) end = cut
            }
            val text = normalized.substring(pos, end).trim()
            if (text.isNotEmpty()) chunks.add(TextChunk(chunks.size, text, pos, end))
            pos = end
        }
        return Chunking(chunks, truncated = pos < n && normalized.substring(pos).isNotBlank())
    }

    data class Chunking(val chunks: List<TextChunk>, val truncated: Boolean)

    private fun breakPoint(s: String, start: Int, hardEnd: Int): Int {
        val minEnd = start + TARGET_CHARS / 2
        val window = s.substring(start, hardEnd)
        val para = window.lastIndexOf("\n\n")
        if (para + start >= minEnd) return start + para + 2
        var sentence = -1
        for (m in Regex("[.!?।]\\s").findAll(window)) sentence = m.range.last + 1
        if (sentence + start >= minEnd) return start + sentence
        val line = window.lastIndexOf('\n')
        if (line + start >= minEnd) return start + line + 1
        val space = window.lastIndexOf(' ')
        if (space + start >= minEnd) return start + space + 1
        return hardEnd
    }
}
