package com.ashura.tutor.domain

import com.ashura.tutor.domain.library.ImportCheck
import com.ashura.tutor.domain.library.TextChunker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TextChunkerTest {
    @Test fun acceptsSupportedFormatsAndRejectsOthers() {
        assertEquals(ImportCheck.Ok, TextChunker.check("text/plain", "a.txt", 10))
        assertEquals(ImportCheck.Ok, TextChunker.check("application/octet-stream", "notes.md", 10))
        assertEquals(ImportCheck.Ok, TextChunker.check(null, "notes.MD", 10))
        assertEquals(ImportCheck.Ok, TextChunker.check("application/octet-stream", "notes.docx", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check(null, "marks.XLSX", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check("application/octet-stream", "deck.pptx", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check("application/pdf", "a.pdf", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check(null, "scan.PNG", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check("text/csv", "marks.csv", 100))
        assertEquals(ImportCheck.Ok, TextChunker.check(null, "marks.TSV", 100))
        assertEquals(TextChunker.Kind.DOCX, TextChunker.detectKind(null, "a.docx"))
        assertEquals(TextChunker.Kind.CSV, TextChunker.detectKind(null, "a.csv"))
        assertEquals(TextChunker.Kind.CSV, TextChunker.detectKind("text/csv", null))
        assertEquals(TextChunker.Kind.CSV, TextChunker.detectKind("text/tab-separated-values", null))
        assertEquals(TextChunker.Kind.XLSX, TextChunker.detectKind(null, "a.xlsx"))
        assertEquals(TextChunker.Kind.PPTX, TextChunker.detectKind(null, "a.pptx"))
        assertEquals(TextChunker.Kind.PDF, TextChunker.detectKind("application/pdf", null))
        assertEquals(TextChunker.Kind.IMAGE, TextChunker.detectKind("image/jpeg", null))
        assertEquals(TextChunker.Kind.TEXT, TextChunker.detectKind("text/markdown", null))
        assertTrue(TextChunker.check("application/pdf", "a.pdf", TextChunker.MAX_PDF_BYTES + 1L) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("image/png", "a.png", TextChunker.MAX_IMAGE_BYTES + 1L) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("application/octet-stream", "a.exe", 10) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("application/msword", "a.doc", 10) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("text/plain", "a.txt", TextChunker.MAX_BYTES + 1L) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("text/plain", "a.txt", 0) is ImportCheck.Rejected)
        assertTrue(TextChunker.check("application/octet-stream", "a.docx", 2) is ImportCheck.Rejected)
    }

    @Test fun normalizeStripsBomControlsAndCollapsesBlankLines() {
        assertEquals("a\nb\n\nc", TextChunker.normalize("\uFEFFa\r\nb\r\n\r\n\r\n\r\nc\u0000\u0007  "))
    }

    @Test fun binaryLookingContentIsDetected() {
        assertTrue(TextChunker.looksLikeText("hello world"))
        assertFalse(TextChunker.looksLikeText("a\u0000b\u0000\u0000c"))
        assertFalse(TextChunker.looksLikeText(""))
    }

    @Test fun chunksRespectLimitsAndCoverAllText() {
        val para = "Newton's first law states that an object stays at rest. ".repeat(12).trim()
        val text = List(30) { "$para" }.joinToString("\n\n")
        val r = TextChunker.chunk(TextChunker.normalize(text))
        assertFalse(r.truncated)
        assertTrue(r.chunks.size > 10)
        r.chunks.forEachIndexed { i, c ->
            assertEquals(i, c.ordinal)
            assertTrue("chunk too long: ${c.text.length}", c.text.length <= TextChunker.MAX_CHARS)
            assertTrue(c.text.isNotBlank())
        }
        val rebuilt = r.chunks.joinToString("") { it.text.filterNot(Char::isWhitespace) }
        assertEquals(TextChunker.normalize(text).filterNot(Char::isWhitespace), rebuilt)
    }

    @Test fun offsetsPointBackIntoTheSource() {
        val src = TextChunker.normalize("First paragraph here.\n\nSecond paragraph follows. ".repeat(80))
        TextChunker.chunk(src).chunks.forEach { c ->
            assertEquals(c.text, src.substring(c.startOffset, c.endOffset).trim())
        }
    }

    @Test fun unbrokenTextStillSplitsAndTruncationIsReported() {
        val blob = "x".repeat(TextChunker.MAX_CHARS * 3 + 5)
        assertEquals(4, TextChunker.chunk(blob).chunks.size)
        val huge = "word ".repeat(TextChunker.MAX_CHUNKS * TextChunker.MAX_CHARS / 4)
        val r = TextChunker.chunk(huge)
        assertEquals(TextChunker.MAX_CHUNKS, r.chunks.size)
        assertTrue(r.truncated)
    }

    @Test fun ocrPageLabelsStartANewChunk() {
        val text = "[Page 1]\nembedded text\n" +
            "[Page 2 · OCR: check against the original scan]\n" + "x ".repeat(600) + "\n" +
            "[Page 3 · OCR: check against the original scan]\n" + "y ".repeat(600)
        val chunks = TextChunker.chunk(TextChunker.normalize(text)).chunks
        assertTrue(chunks.any { it.text.startsWith("[Page 2 · OCR") })
        assertTrue(chunks.any { it.text.startsWith("[Page 3 · OCR") })
    }

    @Test fun nepaliDandaIsASentenceBoundary() {
        val s = "यो एउटा वाक्य हो। ".repeat(200)
        val r = TextChunker.chunk(TextChunker.normalize(s))
        assertTrue(r.chunks.all { it.text.endsWith("।") })
    }

    @Test fun normalizeMatchesLegacyBehaviourOnEdgeCases() {
        assertEquals("a\nb", TextChunker.normalize("a  \t \nb"))
        assertEquals("a\n\nb", TextChunker.normalize("a\n \n\t\n  \n\nb"))
        assertEquals("a b", TextChunker.normalize("  a b  "))
        assertEquals("", TextChunker.normalize(" \n\n \t "))
        assertEquals("x\n\ny", TextChunker.normalize("x\r\r\ry"))
    }

    @Test fun normalizeIsLinearOnWhitespaceBombs() {
        // 2 MB of spaces took ~hours with the old regex; must be near-instant now.
        val t0 = System.nanoTime()
        assertEquals("", TextChunker.normalize(" ".repeat(2 * 1024 * 1024)))
        assertEquals("x", TextChunker.normalize(" \t".repeat(1_000_000) + "x" + " ".repeat(500_000)))
        assertTrue("took too long", (System.nanoTime() - t0) / 1_000_000 < 3_000)
    }
}
