package com.ashura.tutor.domain

import com.ashura.tutor.domain.library.CsvExtractor
import com.ashura.tutor.domain.library.SectionLabel
import com.ashura.tutor.domain.library.TextChunker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CsvExtractorTest {
    @Test fun quotedFieldsEscapedQuotesAndNewlinesSurvive() {
        val csv = "Name,Quote\n" +
            "Alice,\"She said \"\"hello\"\"\"\n" +
            "Bob,\"two\nlines\"\n"
        val result = CsvExtractor.extract(csv)
        assertTrue(result.text.startsWith("[Sheet: CSV]"))
        assertTrue(result.text.contains("A1: Name"))
        assertTrue(result.text.contains("B2: She said \"hello\""))
        assertTrue(result.text.contains("B3: two lines"))
        assertFalse(result.truncated)
    }

    @Test fun tsvIsDetectedAndKeepsCellReferences() {
        val tsv = "Subject\tScore\nMaths\t92\nScience\t88"
        val result = CsvExtractor.extract(tsv)
        assertTrue(result.text.contains("[Sheet: CSV]"))
        assertTrue(result.text.contains("A1: Subject"))
        assertTrue(result.text.contains("B2: 92"))
        assertTrue(result.text.contains("B3: 88"))
    }

    @Test fun semicolonDelimiterIsDetected() {
        val result = CsvExtractor.extract("Name;Mark\nAlice;84")
        assertTrue(result.text.contains("A1: Name"))
        assertTrue(result.text.contains("B2: 84"))
    }

    @Test fun rowAndColumnLimitsAreBounded() {
        val manyColumns = (1..200).joinToString(",") { "c$it" }
        val result = CsvExtractor.extract(manyColumns)
        // The 100th column is CV, the 101st is dropped.
        assertTrue(result.text.contains("CV1: c100"))
        assertFalse(result.text.contains("CW1"))
    }

    @Test fun emptyAndBlankRowsAreIgnored() {
        val result = CsvExtractor.extract("\n\nname,age\n\n,,\nAlice,20\n")
        assertTrue(result.text.contains("A1: name"))
        assertTrue(result.text.contains("A2: Alice"))
        assertFalse(result.text.contains("A3:"))
    }

    @Test fun csvProvenanceIsRecognisedBySectionLabelAndChunker() {
        val raw = "a,b\n1,2\n" + (1..80).joinToString("\n") { "row$it,value$it" }
        val text = TextChunker.normalize(CsvExtractor.extract(raw).text)
        assertEquals("Sheet: CSV", SectionLabel.forChunk(text))
        val chunks = TextChunker.chunk(text).chunks
        assertTrue(chunks.isNotEmpty())
        assertTrue(chunks.first().text.startsWith("[Sheet: CSV]"))
        // Row references must stay intact inside a chunk rather than being cut mid-line.
        assertTrue(chunks.joinToString("\n") { it.text }.contains("A4: row2"))
    }

    @Test fun columnNameHandlesRollover() {
        assertEquals("A", CsvExtractor.columnName(1))
        assertEquals("Z", CsvExtractor.columnName(26))
        assertEquals("AA", CsvExtractor.columnName(27))
        assertEquals("AZ", CsvExtractor.columnName(52))
        assertEquals("BA", CsvExtractor.columnName(53))
    }
}
