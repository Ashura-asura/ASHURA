package com.ashura.tutor.domain.runtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AnswerSanitizerTest {

    @Test fun removesPromptPlaceholdersFromPastedDampedOscillationAnswer() {
        val raw = """
            **ANSWER:**
            To fully derive a damped oscillation, start by considering the forces acting on the system.
            The equation is m*x'' + kx = F_damping(t).

            **STEPS:**
            1. Write the differential equation for damped oscillation.
            2. Incorporate damping into the equation.

            **CHECK:**
            What is the general form of the damped oscillation equation?
            If unsure, say so.

            **EVIDENCE:**
            [Ref] [n] from trusted source: "Damped Oscillations involve the equation."
        """.trimIndent()

        val clean = AnswerSanitizer.clean(raw)

        assertFalse(clean.contains("[n]"))
        assertFalse(clean.contains("[Ref]"))
        assertFalse(clean.contains("EVIDENCE", ignoreCase = true))
        assertFalse(clean.contains("If unsure, say so"))
        assertFalse(clean.contains("trusted source", ignoreCase = true))
        assertTrue(clean.contains("Write the differential equation"))
    }

    @Test fun removesPromptPlaceholdersFromPastedZenerAnswer() {
        val raw = """
            **STEPS:**
            1. Begin with the Zener diode's operating characteristics.
            2. Write the energy balance equation.
            3. Use the diode's current-time response.

            **CHECK:**
            What is the Zener diode's main function?

            **evidence**: [n] using its id.
        """.trimIndent()

        val clean = AnswerSanitizer.clean(raw)

        assertFalse(clean.contains("[n]"))
        assertFalse(clean.contains("using its id", ignoreCase = true))
        assertFalse(clean.contains("evidence", ignoreCase = true))
        assertTrue(clean.contains("Zener diode's operating characteristics"))
    }

    @Test fun removesEchoedIdentityAnswerPlaceholdersButKeepsItsAnswerText() {
        val raw = "**evidence**: [n] using its id. ANSWER: I am a patient tutor, and I am always here to support you."

        val clean = AnswerSanitizer.clean(raw)

        assertFalse(clean.contains("[n]"))
        assertFalse(clean.contains("using its id", ignoreCase = true))
        assertFalse(clean.contains("evidence", ignoreCase = true))
        assertTrue(clean.startsWith("ANSWER: I am a patient tutor"))
    }

    @Test fun keepsRealNumberedCitations() {
        val raw = "ATP is made in mitochondria [1] and in chloroplasts [2]."
        assertEquals(raw, AnswerSanitizer.clean(raw))
    }

    @Test fun leavesOrdinaryAnswerUnchanged() {
        val raw = "The derivative of sin x is cos x.\n\nSTEPS:\n1. Apply the limit definition."
        assertEquals(raw, AnswerSanitizer.clean(raw))
    }

    @Test fun collapsesWhitespaceLeftBehindByRemovedPlaceholders() {
        assertEquals("Citing . Done.", AnswerSanitizer.clean("Citing [n] . Done."))
    }

    @Test fun removesHiddenThinkingBlocksAndPlanningSections() {
        val raw = """
            <think>The learner asks about damping, so I should compute roots first.</think>
            Thinking Process:
            Consider three cases and pick the formula.
            ANSWER: The motion decays as e^(-γt) cos(ωt).
            STEPS:
            1. Write the equation.
        """.trimIndent()

        val clean = AnswerSanitizer.clean(raw)

        assertFalse(clean.contains("learner asks", ignoreCase = true))
        assertFalse(clean.contains("Thinking Process", ignoreCase = true))
        assertFalse(clean.contains("three cases", ignoreCase = true))
        assertTrue(clean.startsWith("ANSWER: The motion decays"))
    }

    @Test fun removesLeakedChatTemplateTokens() {
        val clean = AnswerSanitizer.clean("Answer<|im_end|><|im_start|>assistant")
        assertFalse(clean.contains("<|"))
        assertTrue(clean.startsWith("Answer"))
    }
}
