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
    const val MAX_CHUNKS = 2_000
    const val TARGET_CHARS = 900
    const val MAX_CHARS = 1_400
    private val allowedMime = setOf("text/plain", "text/markdown", "text/x-markdown")

    fun check(mimeType: String?, displayName: String?, sizeBytes: Long?): ImportCheck {
        val name = displayName.orEmpty().lowercase()
        val mime = mimeType.orEmpty().lowercase()
        val extOk = name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".markdown")
        // Some providers report application/octet-stream for .md; accept only if the extension is clearly text.
        val mimeOk = mime in allowedMime || (mime == "application/octet-stream" && extOk) || (mime.isEmpty() && extOk)
        if (!mimeOk) return ImportCheck.Rejected("Only plain text (.txt) and Markdown (.md) files are supported in this build.")
        if (sizeBytes != null && sizeBytes > MAX_BYTES) return ImportCheck.Rejected("File is larger than ${MAX_BYTES / (1024 * 1024)} MB.")
        if (sizeBytes != null && sizeBytes == 0L) return ImportCheck.Rejected("File is empty.")
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
            val end = if (hardEnd == n) n else breakPoint(normalized, pos, hardEnd)
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
