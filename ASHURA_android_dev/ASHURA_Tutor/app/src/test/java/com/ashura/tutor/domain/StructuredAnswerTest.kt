package com.ashura.tutor.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The parser must recover the model's ANSWER/STEPS/CHECK structure when it appears, and must never
 * lose text when a small model ignores the requested format (spec §1.3, §3.3).
 */
class StructuredAnswerTest {

    @Test fun parsesAllThreeMarkers() {
        val parsed = StructuredAnswer.parse(
            """
            ANSWER: Photosynthesis converts light into chemical energy.
            STEPS:
            1. Light is absorbed by chlorophyll.
            2. Water is split and oxygen is released.
            3. Carbon dioxide is fixed into sugar.
            CHECK: What gas does the plant release?
            """.trimIndent()
        )
        assertEquals("Photosynthesis converts light into chemical energy.", parsed.answer)
        assertEquals(3, parsed.steps.size)
        assertEquals("Light is absorbed by chlorophyll.", parsed.steps[0])
        assertEquals("Carbon dioxide is fixed into sugar.", parsed.steps[2])
        assertEquals("What gas does the plant release?", parsed.check)
        assertTrue(parsed.isStructured)
    }

    @Test fun handlesBoldMarkersAndPreamble() {
        val parsed = StructuredAnswer.parse(
            """
            Sure, here is an explanation.

            **ANSWER:** Force equals mass times acceleration.
            **STEPS:**
            - Identify the mass.
            - Identify the acceleration.
            **CHECK:** What are the units of force?
            """.trimIndent()
        )
        assertEquals("Sure, here is an explanation.", parsed.preamble)
        assertEquals("Force equals mass times acceleration.", parsed.answer)
        assertEquals(listOf("Identify the mass.", "Identify the acceleration."), parsed.steps)
        assertEquals("What are the units of force?", parsed.check)
    }

    @Test fun keepsPlainTextInsteadOfDroppingIt() {
        val parsed = StructuredAnswer.parse("  The sky looks blue because of Rayleigh scattering.  ")
        assertNull(parsed.answer)
        assertEquals("The sky looks blue because of Rayleigh scattering.", parsed.preamble)
        assertTrue(parsed.steps.isEmpty())
        assertNull(parsed.check)
        assertFalse(parsed.isStructured)
    }

    @Test fun partialMarkersStillParse() {
        val parsed = StructuredAnswer.parse("ANSWER: Yes.\nCHECK: Can you give an example?")
        assertEquals("Yes.", parsed.answer)
        assertEquals("Can you give an example?", parsed.check)
        assertTrue(parsed.steps.isEmpty())
    }

    @Test fun markerLikeProseIsNotMistakenForASection() {
        val parsed = StructuredAnswer.parse("The word ANSWER: appears in the middle of this sentence.")
        assertNull(parsed.answer)
        assertFalse(parsed.isStructured)
    }

    @Test fun longDerivationsKeepAllTheirStepsUpToTheSafetyCap() {
        val steps = (1..12).joinToString("\n") { "$it. Step $it" }
        val parsed = StructuredAnswer.parse("ANSWER: Done.\nSTEPS:\n$steps")
        assertEquals(12, parsed.steps.size)
        assertEquals("Step 1", parsed.steps.first())
    }

    @Test fun blankSectionsAreIgnored() {
        val parsed = StructuredAnswer.parse("ANSWER:\nSTEPS:\nCHECK: Try one example.")
        assertNull(parsed.answer)
        assertTrue(parsed.steps.isEmpty())
        assertEquals("Try one example.", parsed.check)
    }

    @Test fun normalisesWindowsLineEndings() {
        val parsed = StructuredAnswer.parse("ANSWER: One.\r\nSTEPS:\r\n1. Two.\r\nCHECK: Three?")
        assertEquals("One.", parsed.answer)
        assertEquals(listOf("Two."), parsed.steps)
        assertEquals("Three?", parsed.check)
    }
}
