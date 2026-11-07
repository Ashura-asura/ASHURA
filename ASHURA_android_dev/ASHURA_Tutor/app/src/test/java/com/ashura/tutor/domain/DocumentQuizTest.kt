package com.ashura.tutor.domain

import com.ashura.tutor.domain.library.GroundingPolicy
import com.ashura.tutor.domain.library.PassageRef
import com.ashura.tutor.domain.library.QuizBuilder
import com.ashura.tutor.domain.library.QuizKind
import com.ashura.tutor.domain.library.SectionLabel
import com.ashura.tutor.domain.library.TextChunker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DocumentQuizTest {

    private val note = TextChunker.chunk(TextChunker.normalize(
        """
        [Page 1]
        Photosynthesis is the process by which plants convert light energy into chemical energy stored in glucose.
        Chloroplasts are the organelles where photosynthesis takes place.
        The green pigment chlorophyll absorbs light most strongly in the blue and red parts of the spectrum.

        [Page 2]
        Cellular respiration is the process that releases energy from glucose inside the mitochondria.
        Mitochondria are membrane-bound organelles that contain their own DNA and ribosomes.
        ATP is the molecule that carries usable energy inside every living cell.

        [Page 3]
        Enzymes are proteins that speed up chemical reactions without being consumed.
        The active site is the region of an enzyme where the substrate binds.
        Temperature and pH affect enzyme activity by changing the shape of the active site.
        """.trimIndent()
    )).chunks

    @Test fun sectionLabelsAcceptOnlyExtractorMarkers() {
        assertEquals("Page 3", SectionLabel.forChunk("[Page 3]\nSome text"))
        assertEquals("Slide 2", SectionLabel.forChunk("[Slide 2]\nTitle"))
        assertEquals("Sheet: Marks", SectionLabel.forChunk("[Sheet: Marks]\n1,2,3"))
        assertEquals("Image 1", SectionLabel.forChunk("[Image 1]\nOCR text"))
        assertEquals("Notes", SectionLabel.forChunk("[Notes]\nText"))
        assertNull(SectionLabel.forChunk("[not a source]\nText"))
        assertNull(SectionLabel.forChunk("Text without a marker"))
    }

    @Test fun chunkingStartsANewChunkAtEveryProvenanceLabel() {
        val chunks = TextChunker.chunk(TextChunker.normalize(
            "[Page 1]\nAlpha beta gamma.\n\n[Page 2]\nDelta epsilon zeta.\n\n[Slide 3]\nEta theta iota."
        )).chunks
        assertEquals(3, chunks.size)
        assertEquals(listOf("Page 1", "Page 2", "Slide 3"), chunks.mapNotNull { SectionLabel.forChunk(it.text) })
    }

    @Test fun groundingCitationsIncludePageSlideAndSheetLabels() {
        val grounded = GroundingPolicy.select(
            listOf(
                PassageRef("Notes", 0, "Cells are the basic unit of life.", "Page 3"),
                PassageRef("Slides", 1, "Force equals mass times acceleration.", "Slide 2"),
                PassageRef("Marks", 2, "Total: 92", "Sheet: Marks"),
                PassageRef("Plain", 3, "No structure here.")
            ),
            maxPassages = 4
        )
        assertEquals(
            listOf(
                "Notes · Page 3 · passage 1",
                "Slides · Slide 2 · passage 2",
                "Marks · Sheet: Marks · passage 3",
                "Plain · passage 4"
            ),
            grounded.snippets.map { it.sourceLabel }
        )
    }

    @Test fun quizBuilderProducesAMixedSetAcrossEveryPage() {
        val quiz = QuizBuilder.build(note, "Biology notes", 20)
        assertTrue("expected a full set, got ${quiz.size}", quiz.size in 18..20)

        val kinds = quiz.groupingBy { it.kind }.eachCount()
        assertTrue("no cloze items", (kinds[QuizKind.CLOZE] ?: 0) >= 6)
        assertTrue("no definitions", (kinds[QuizKind.DEFINITION] ?: 0) >= 3)
        assertTrue("no explanations", (kinds[QuizKind.EXPLANATION] ?: 0) >= 2)
        assertTrue("too many cloze items", (kinds[QuizKind.CLOZE] ?: 0) <= QuizBuilder.MAX_CLOZE)

        val sections = quiz.mapNotNull { it.section }.toSet()
        assertTrue("page 1 missing from $sections", "Page 1" in sections)
        assertTrue("page 2 missing from $sections", "Page 2" in sections)
        assertTrue("page 3 missing from $sections", "Page 3" in sections)

        quiz.forEach { item ->
            assertTrue("blank prompt", item.prompt.isNotBlank())
            assertTrue("blank answer", item.answer.isNotBlank())
            assertTrue("missing provenance", item.explanation?.contains("Biology notes") == true)
            if (item.kind == QuizKind.CLOZE) {
                assertFalse(item.selfAssessed)
                assertEquals("one blank per cloze", 1, Regex("______").findAll(item.prompt).count())
            } else {
                assertTrue("written answers are self-assessed", item.selfAssessed)
            }
        }
    }

    @Test fun quizBuilderNeverRepeatsAPromptOrTerm() {
        val quiz = QuizBuilder.build(note, "Biology notes", 40)
        assertEquals(quiz.map { it.prompt.lowercase() }.distinct().size, quiz.size)
        val definitionTerms = quiz.filter { it.kind == QuizKind.DEFINITION }
            .map { it.prompt.lowercase() }
        assertEquals(definitionTerms.distinct().size, definitionTerms.size)
        val explanationTopics = quiz.filter { it.kind == QuizKind.EXPLANATION }
            .map { it.prompt.lowercase() }
        assertEquals(explanationTopics.distinct().size, explanationTopics.size)
        assertTrue(quiz.count { it.kind == QuizKind.CLOZE } <= QuizBuilder.MAX_CLOZE)
        assertTrue(quiz.count { it.kind == QuizKind.DEFINITION } <= QuizBuilder.MAX_DEFINITIONS)
    }

    @Test fun tinyAndEmptyNotesAreHandledWithoutInventingQuestions() {
        assertTrue(QuizBuilder.build(emptyList(), "Empty").isEmpty())
        val oneLine = TextChunker.chunk(TextChunker.normalize("Short note.")).chunks
        val quiz = QuizBuilder.build(oneLine, "Short")
        assertTrue(quiz.size <= 1)
        quiz.forEach { assertTrue(it.prompt.isNotBlank() && it.answer.isNotBlank()) }
    }

    @Test fun quizzesCanBeBuiltFromSpreadsheetAndSlideMarkers() {
        val sheets = TextChunker.chunk(TextChunker.normalize(
            """
            [Sheet: Marks]
            Total marks are the sum of every question score in the exam.
            Percentage is the total marks divided by the maximum marks.

            [Sheet: Students]
            Enrollment is the process of adding a student to the class register.
            Attendance is the number of classes a student actually attended.
            """.trimIndent()
        )).chunks
        val quiz = QuizBuilder.build(sheets, "Class sheet", 10)
        assertTrue(quiz.isNotEmpty())
        assertTrue(quiz.all { it.section == "Sheet: Marks" || it.section == "Sheet: Students" })
        assertTrue(quiz.any { it.kind == QuizKind.DEFINITION })
    }
}
