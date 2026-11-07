package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import com.ashura.tutor.domain.export.Json
import com.ashura.tutor.domain.library.ClozeGenerator
import com.ashura.tutor.domain.library.TextChunker
import com.ashura.tutor.domain.math.EvalResult
import com.ashura.tutor.domain.math.ExpressionEvaluator
import com.ashura.tutor.domain.runtime.ModelFileVerifier
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.RamTier
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream

class ExportAndQuizTest {
    @Test fun jsonEscapesAndNestsCorrectly() {
        val out = Json.write(mapOf("a" to "q\"b\\c\n\t\u0001\u007F", "n" to listOf(1, 2L, 3.5, null, true), "e" to emptyMap<String, Any>(), "l" to emptyList<Int>(), "u" to "नेपाली 😀"))
        assertTrue(out.contains("\"q\\\"b\\\\c\\n\\t\\u0001\\u007f\""))
        assertTrue(out.contains("\"नेपाली 😀\""))
        assertTrue(out.contains("3.5"))
        assertTrue(out.contains("\"e\": {}"))
        assertTrue(out.contains("\"l\": []"))
    }

    @Test fun jsonRejectsNonFiniteNumbersAndBadKeys() {
        for (bad in listOf<Any>(Double.NaN, Double.POSITIVE_INFINITY, mapOf(1 to "x"), object {})) {
            try { Json.write(bad); throw AssertionError("expected failure for $bad") } catch (_: IllegalArgumentException) { }
        }
    }

    private val note = TextChunker.chunk(TextChunker.normalize(
        "Mitochondria produce most of the chemical energy a cell needs. Mitochondria contain their own DNA and ribosomes.\n\n" +
        "Photosynthesis converts light energy into chemical energy stored in glucose molecules. Chloroplasts perform photosynthesis in plant cells.\n\n" +
        "Ribosomes assemble amino acids into proteins following instructions from messenger RNA."
    )).chunks

    @Test fun clozeBlanksOneRealWordPerSentenceAndSpreadsAcrossPassages() {
        val items = ClozeGenerator.generate(note, max = 5)
        assertTrue(items.size >= 2)
        items.forEach {
            assertEquals(1, Regex("______").findAll(it.prompt).count())
            // Filling the blank back in must give a sentence that exists in the note.
            assertTrue(note.any { c -> c.text.contains(it.prompt.replace("______", it.answer)) })
            assertTrue(it.hint.contains("${it.answer.length} letters"))
        }
        assertEquals(items.map { it.answer.lowercase() }.distinct().size, items.size)
    }

    @Test fun clozeIsDeterministicAndHandlesTinyInput() {
        assertEquals(ClozeGenerator.generate(note, 5), ClozeGenerator.generate(note, 5))
        assertTrue(ClozeGenerator.generate(emptyList()).isEmpty())
        assertTrue(ClozeGenerator.generate(TextChunker.chunk("Too short.").chunks).isEmpty())
    }

    @Test fun clozeAnswersAreCheckedLeniently() {
        val item = ClozeGenerator.generate(note, 1).first()
        val q = PracticeQuestion("note:x:q1", "note:x", item.prompt, item.answer)
        val checker = AnswerChecker()
        assertEquals(Verdict.CORRECT, checker.check(q, item.answer.uppercase()).verdict)
        assertEquals(Verdict.CORRECT, checker.check(q, " ${item.answer}. ").verdict)
        assertEquals(Verdict.INCORRECT, checker.check(q, "wrong").verdict)
    }

    @Test fun devanagariDigitsAreAcceptedInAnswersAndCalculator() {
        val q = SeedCurriculum.fractions.practice[1] // 3/4 of 20 = 15
        assertEquals(Verdict.CORRECT, AnswerChecker().check(q, "१५").verdict)
        val r = ExpressionEvaluator.evaluate("१२ + ३ × २") as EvalResult.Value
        assertEquals("18", ExpressionEvaluator.format(r.value, r.exact))
        assertTrue(CalculatorTool().handles("१२ + ३"))
    }

    @Test fun sha256MatchesKnownVectorsAndManifestVerification() {
        val abc = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        assertEquals(abc, ModelFileVerifier.sha256Hex(ByteArrayInputStream("abc".toByteArray())))
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", ModelFileVerifier.sha256Hex(ByteArrayInputStream(ByteArray(0))))
        val m = ModelManifest("m", "rev", abc, abc, "chatml", "Q4", 2048, "Apache-2.0", RamTier.CONSTRAINED)
        assertEquals(ModelFileVerifier.Verdict.Valid, ModelFileVerifier.verify(ByteArrayInputStream("abc".toByteArray()), m))
        assertTrue(ModelFileVerifier.verify(ByteArrayInputStream("abd".toByteArray()), m) is ModelFileVerifier.Verdict.Invalid)
        assertTrue(ModelFileVerifier.verify(ByteArrayInputStream("abc".toByteArray()), m.copy(artifactSha256 = "zz")) is ModelFileVerifier.Verdict.Invalid)
    }

    @Test fun storageCheckKeepsAReserve() {
        val gib = 1L shl 30
        assertTrue(ModelFileVerifier.hasSpaceFor(2 * gib, 4 * gib))
        assertFalse(ModelFileVerifier.hasSpaceFor(2 * gib, 2 * gib + 1))
        assertFalse(ModelFileVerifier.hasSpaceFor(0, 10 * gib))
    }
}
