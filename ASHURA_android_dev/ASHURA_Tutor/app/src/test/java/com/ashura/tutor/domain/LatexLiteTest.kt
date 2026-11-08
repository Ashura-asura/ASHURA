package com.ashura.tutor.domain

import com.ashura.tutor.domain.text.LatexLite
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LatexLiteTest {

    @Test fun rendersThePastedDampedOscillationEquationAsReadableText() {
        val raw = "\$\$m\\cdot\\ddot{x} + kx = F_{\\text{damping}}(t)\$\$"
        val out = LatexLite.render(raw)
        assertFalse(out.contains("\\"))
        assertFalse(out.contains("\$"))
        assertTrue(out.contains("m·ẍ"))
        assertTrue(out.contains("kx"))
    }

    @Test fun convertsFractionsRootsAndGreekLetters() {
        val out = LatexLite.render("\$\\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}\$ and \$\\omega_0^2\$")
        assertTrue(out.contains("(-b ± √(b² - 4ac))/(2a)"))
        assertTrue(out.contains("ω₀²"))
    }

    @Test fun convertsInlineDelimitersAndKeepsSurroundingProse() {
        val out = LatexLite.render("The energy is \$E = mc^2\$ exactly.")
        assertEquals("The energy is E = mc² exactly.", out)
    }

    @Test fun leavesPlainTextUntouched() {
        val text = "The derivative of sin x is cos x."
        assertEquals(text, LatexLite.render(text))
    }

    @Test fun unknownCommandsLoseTheBackslashButKeepTheWord() {
        val out = LatexLite.render("\\unknowncommand{x} stays readable")
        assertTrue(out.contains("unknowncommand{x}"))
        assertFalse(out.contains("\\unknowncommand"))
    }
}
