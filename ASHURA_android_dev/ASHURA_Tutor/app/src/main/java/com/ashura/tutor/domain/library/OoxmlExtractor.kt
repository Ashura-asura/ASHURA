package com.ashura.tutor.domain.library

import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserException
import org.xmlpull.v1.XmlPullParserFactory
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.util.zip.ZipException
import java.util.zip.ZipInputStream

/**
 * Dependency-free OOXML text extraction for imported learner notes (spec §10.1).
 *
 * Imported documents are untrusted evidence: this code reads text only, never evaluates formulas,
 * macros or embedded objects, never writes to disk, and never follows external parts. Every loop is
 * bounded, and both the compressed input (enforced by the caller) and the expanded archive are capped
 * so a zip bomb cannot exhaust memory or CPU.
 */
object OoxmlExtractor {

    enum class Kind { DOCX, XLSX, PPTX }

    sealed interface Result {
        data class Success(val text: String, val truncated: Boolean) : Result
        data class Failure(val reason: String) : Result
    }

    /** Hard limits. A 2 MB compressed note can expand, but never without bound. */
    const val MAX_ENTRIES = 1_024
    const val MAX_TOTAL_UNCOMPRESSED = 32L * 1024 * 1024
    const val MAX_PART_BYTES = 8L * 1024 * 1024
    const val MAX_TEXT_CHARS = 3_000_000

    private val slidePart = Regex("^ppt/slides/slide\\d+\\.xml$")
    private val notesPart = Regex("^ppt/notesSlides/notesSlide\\d+\\.xml$")
    private val sheetPart = Regex("^xl/worksheets/sheet\\d+\\.xml$")
    private val docxExtraPart = Regex("^word/(header\\d*|footer\\d*|footnotes|endnotes)\\.xml$")
    private val numbers = Regex("\\d+")

    fun extract(kind: Kind, input: InputStream): Result {
        val parts = try {
            readParts(kind, input)
        } catch (e: ZipException) {
            return Result.Failure("This file is not a valid Office document (corrupt or encrypted archive).")
        } catch (e: TooLargeException) {
            return Result.Failure(e.message ?: "This document expands to too much data to import safely.")
        } catch (e: IOException) {
            return Result.Failure("Could not read this Office document: ${e.message ?: "I/O error"}")
        }

        return try {
            when (kind) {
                Kind.DOCX -> extractDocx(parts)
                Kind.XLSX -> extractXlsx(parts)
                Kind.PPTX -> extractPptx(parts)
            }
        } catch (e: MalformedPartException) {
            Result.Failure(e.message ?: "This Office document contains malformed XML.")
        } catch (e: XmlPullParserException) {
            Result.Failure("This Office document contains malformed XML.")
        } catch (e: IOException) {
            Result.Failure("Could not read this Office document: ${e.message ?: "I/O error"}")
        }
    }

    // ------------------------------------------------------------------ archive

    private fun readParts(kind: Kind, input: InputStream): Map<String, ByteArray> {
        val parts = LinkedHashMap<String, ByteArray>()
        var entries = 0
        var total = 0L
        ZipInputStream(input.buffered()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (++entries > MAX_ENTRIES) throw TooLargeException("This document has too many archive entries.")
                val keep = !entry.isDirectory && wanted(kind, entry.name)
                val kept = drain(zip, keep)
                total += kept.read
                if (total > MAX_TOTAL_UNCOMPRESSED) {
                    throw TooLargeException("This document expands to more than ${MAX_TOTAL_UNCOMPRESSED / (1024 * 1024)} MB.")
                }
                kept.bytes?.let { parts[entry.name] = it }
                zip.closeEntry()
            }
        }
        return parts
    }

    private class Drained(val bytes: ByteArray?, val read: Long)

    private fun drain(zip: ZipInputStream, keep: Boolean): Drained {
        if (!keep) {
            // Still stream through unwanted data so the global expansion cap applies to it.
            val buf = ByteArray(16 * 1024)
            var read = 0L
            while (true) {
                val n = zip.read(buf)
                if (n < 0) break
                read += n
                if (read > MAX_TOTAL_UNCOMPRESSED) throw TooLargeException()
            }
            return Drained(null, read)
        }
        val out = ByteArrayOutputStream()
        val buf = ByteArray(16 * 1024)
        var read = 0L
        while (true) {
            val n = zip.read(buf)
            if (n < 0) break
            read += n
            if (read > MAX_PART_BYTES) {
                throw TooLargeException("One part of this document is larger than ${MAX_PART_BYTES / (1024 * 1024)} MB.")
            }
            out.write(buf, 0, n)
        }
        return Drained(out.toByteArray(), read)
    }

    private fun wanted(kind: Kind, name: String): Boolean = when (kind) {
        Kind.DOCX -> name == "word/document.xml" || docxExtraPart.matches(name)
        Kind.XLSX ->
            name == "xl/sharedStrings.xml" || name == "xl/workbook.xml" ||
                name == "xl/_rels/workbook.xml.rels" || sheetPart.matches(name)
        Kind.PPTX -> slidePart.matches(name) || notesPart.matches(name)
    }

    // -------------------------------------------------------------------- DOCX

    private fun extractDocx(parts: Map<String, ByteArray>): Result {
        val main = parts["word/document.xml"]
            ?: return Result.Failure("This .docx file has no readable document part.")
        val sink = Sink()
        docxBody(main, sink)
        parts.keys.filter { it != "word/document.xml" }.sortedWith(partComparator).forEach { name ->
            if (sink.truncated) return@forEach
            sink.blankLine()
            docxBody(parts.getValue(name), sink)
        }
        return finish(sink)
    }

    private fun docxBody(bytes: ByteArray, sink: Sink) {
        var inText = false
        walk(bytes) { event, parser ->
            when (event) {
                XmlPullParser.START_TAG -> when (parser.name) {
                    "t" -> inText = true
                    "tab" -> sink.append('\t')
                    "br", "cr" -> sink.append('\n')
                }
                XmlPullParser.TEXT -> if (inText) sink.append(parser.text)
                XmlPullParser.END_TAG -> when (parser.name) {
                    "t" -> inText = false
                    "p" -> sink.append('\n')
                    "tc" -> sink.append('\t')
                }
            }
        }
    }

    // -------------------------------------------------------------------- PPTX

    private fun extractPptx(parts: Map<String, ByteArray>): Result {
        val slides = parts.keys.filter { slidePart.matches(it) }.sortedWith(partComparator)
        if (slides.isEmpty()) return Result.Failure("This .pptx file has no readable slides.")
        val sink = Sink()
        slides.forEachIndexed { index, name ->
            if (sink.truncated) return@forEachIndexed
            if (index > 0) sink.blankLine()
            sink.append("[Slide ${index + 1}]\n")
            drawingText(parts.getValue(name), sink)
            val notes = "ppt/notesSlides/notesSlide${index + 1}.xml"
            parts[notes]?.let {
                sink.append("\n[Notes]\n")
                drawingText(it, sink)
            }
        }
        return finish(sink)
    }

    private fun drawingText(bytes: ByteArray, sink: Sink) {
        var inText = false
        walk(bytes) { event, parser ->
            when (event) {
                XmlPullParser.START_TAG -> if (parser.name == "t") inText = true
                XmlPullParser.TEXT -> if (inText) sink.append(parser.text)
                XmlPullParser.END_TAG -> when (parser.name) {
                    "t" -> inText = false
                    "p" -> sink.append('\n')
                }
            }
        }
    }

    // -------------------------------------------------------------------- XLSX

    private fun extractXlsx(parts: Map<String, ByteArray>): Result {
        val shared = parts["xl/sharedStrings.xml"]?.let { parseSharedStrings(it) } ?: emptyList()
        val names = sheetNames(parts)
        val sheets = parts.keys.filter { sheetPart.matches(it) }.sortedWith(partComparator)
        if (sheets.isEmpty()) return Result.Failure("This .xlsx file has no readable worksheets.")
        val sink = Sink()
        sheets.forEachIndexed { index, path ->
            if (sink.truncated) return@forEachIndexed
            if (index > 0) sink.blankLine()
            sink.append("[${names[path] ?: "Sheet ${index + 1}"}]\n")
            parseSheet(parts.getValue(path), shared, sink)
        }
        return finish(sink)
    }

    private fun parseSharedStrings(bytes: ByteArray): List<String> {
        val strings = ArrayList<String>()
        var current: StringBuilder? = null
        var inText = false
        walk(bytes) { event, parser ->
            when (event) {
                XmlPullParser.START_TAG -> when (parser.name) {
                    "si" -> current = StringBuilder()
                    "t" -> inText = true
                }
                XmlPullParser.TEXT -> if (inText) current?.append(parser.text)
                XmlPullParser.END_TAG -> when (parser.name) {
                    "t" -> inText = false
                    "si" -> {
                        strings.add(current?.toString().orEmpty())
                        current = null
                    }
                }
            }
        }
        return strings
    }

    private fun parseSheet(bytes: ByteArray, shared: List<String>, sink: Sink) {
        var type: String? = null
        var inValue = false
        var inFormula = false
        var inInlineText = false
        var inlineDepth = 0
        val value = StringBuilder()
        val formula = StringBuilder()
        val inline = StringBuilder()

        walk(bytes) { event, parser ->
            when (event) {
                XmlPullParser.START_TAG -> when (parser.name) {
                    "c" -> {
                        type = attribute(parser, "t")
                        value.setLength(0)
                        formula.setLength(0)
                        inline.setLength(0)
                        inlineDepth = 0
                    }
                    "v" -> inValue = true
                    "f" -> inFormula = true
                    "is" -> inlineDepth++
                    "t" -> if (inlineDepth > 0) inInlineText = true
                }
                XmlPullParser.TEXT -> when {
                    inValue -> value.append(parser.text)
                    inFormula -> formula.append(parser.text)
                    inInlineText -> inline.append(parser.text)
                }
                XmlPullParser.END_TAG -> when (parser.name) {
                    "v" -> inValue = false
                    "f" -> inFormula = false
                    "t" -> inInlineText = false
                    "is" -> if (inlineDepth > 0) inlineDepth--
                    "c" -> {
                        sink.append(cellText(type, value, formula, inline, shared))
                        sink.append('\t')
                    }
                    "row" -> sink.append('\n')
                }
            }
        }
    }

    private fun cellText(
        type: String?,
        value: StringBuilder,
        formula: StringBuilder,
        inline: StringBuilder,
        shared: List<String>
    ): String {
        if (formula.isNotEmpty()) return "=${formula.toString().trim()}"
        return when (type) {
            "s" -> value.toString().trim().toIntOrNull()?.let { shared.getOrNull(it) }.orEmpty()
            "inlineStr" -> inline.toString()
            "b" -> if (value.toString().trim() == "1") "TRUE" else "FALSE"
            else -> value.toString()
        }
    }

    /** Maps worksheet part paths to their workbook sheet names; falls back to numeric labels. */
    private fun sheetNames(parts: Map<String, ByteArray>): Map<String, String> {
        val workbook = parts["xl/workbook.xml"] ?: return emptyMap()
        val rels = parts["xl/_rels/workbook.xml.rels"] ?: return emptyMap()
        val idToName = HashMap<String, String>()
        walk(workbook) { event, parser ->
            if (event == XmlPullParser.START_TAG && parser.name == "sheet") {
                val id = attribute(parser, "id")
                val name = attribute(parser, "name")
                if (!id.isNullOrBlank() && name != null) idToName[id] = name
            }
        }
        val targetToName = HashMap<String, String>()
        walk(rels) { event, parser ->
            if (event == XmlPullParser.START_TAG && parser.name == "Relationship") {
                val id = attribute(parser, "Id")
                val target = attribute(parser, "Target")
                if (id != null && target != null) {
                    val name = idToName[id] ?: return@walk
                    val normalised = if (target.startsWith("/")) target.drop(1) else "xl/$target"
                    targetToName[normalised] = name
                }
            }
        }
        return targetToName
    }

    // ------------------------------------------------------------------- shared

    private fun finish(sink: Sink): Result = Result.Success(sink.text(), sink.truncated)

    private fun walk(bytes: ByteArray, handler: (Int, XmlPullParser) -> Unit) {
        val factory = XmlPullParserFactory.newInstance()
        factory.isNamespaceAware = true
        factory.setFeature(XmlPullParser.FEATURE_PROCESS_DOCDECL, false)
        val parser = factory.newPullParser()
        parser.setInput(ByteArrayInputStream(bytes), null)
        var event = parser.eventType
        while (event != XmlPullParser.END_DOCUMENT) {
            handler(event, parser)
            event = parser.next()
        }
    }

    /** Namespace-aware attribute lookup by local name; covers both `r:id` and plain attributes. */
    private fun attribute(parser: XmlPullParser, localName: String): String? {
        for (i in 0 until parser.attributeCount) {
            if (parser.getAttributeName(i) == localName) return parser.getAttributeValue(i)
        }
        return null
    }

    private val partComparator = Comparator<String> { a, b ->
        a.replace(numbers) { it.value.padStart(12, '0') }
            .compareTo(b.replace(numbers) { it.value.padStart(12, '0') })
    }

    private class Sink {
        private val builder = StringBuilder()
        var truncated = false
            private set

        fun append(value: CharSequence) = append(value, value.length)

        fun append(c: Char) {
            if (builder.length >= MAX_TEXT_CHARS) {
                truncated = true
                return
            }
            builder.append(c)
        }

        private fun append(value: CharSequence, length: Int) {
            if (builder.length >= MAX_TEXT_CHARS) {
                truncated = true
                return
            }
            val remaining = MAX_TEXT_CHARS - builder.length
            if (length <= remaining) {
                builder.append(value)
            } else {
                builder.append(value, 0, remaining)
                truncated = true
            }
        }

        fun blankLine() = append("\n\n")

        fun text(): String = builder.toString()
    }

    private class TooLargeException(message: String = "This document expands to too much data to import safely.") :
        Exception(message)

    private class MalformedPartException(message: String) : Exception(message)
}
