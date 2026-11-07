package com.ashura.tutor.domain

import com.ashura.tutor.domain.math.EvalResult
import com.ashura.tutor.domain.math.ExpressionEvaluator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExpressionEvaluatorTest {

    private fun eval(s: String): String = when (val r = ExpressionEvaluator.evaluate(s)) {
        is EvalResult.Value -> ExpressionEvaluator.format(r.value, r.exact)
        is EvalResult.Error -> "ERR:" + r.message
    }

    @Test fun precedenceAndParentheses() {
        assertEquals("11", eval("3 + 4 * 2"))
        assertEquals("14", eval("(3 + 4) * 2"))
        assertEquals("4", eval("10 - 2 * 3"))
        assertEquals("3", eval("18 / 3 / 2"))
    }

    @Test fun powerIsRightAssociativeAndUnaryMinusLooser() {
        assertEquals("512", eval("2 ^ 3 ^ 2"))
        assertEquals("-4", eval("-2 ^ 2"))
        assertEquals("0.125", eval("2 ^ -3"))
        assertEquals("8", eval("2 ** 3"))
    }

    @Test fun decimalsAreExactNotBinaryFloating() {
        assertEquals("0.3", eval("0.1 + 0.2"))
        assertEquals("1.5", eval("3 / 2"))
    }

    @Test fun nonTerminatingResultsAreMarkedApproximate() {
        assertTrue(eval("1 / 3").startsWith("≈ 0.333333333333"))
        assertEquals("≈ 1.41421356237", eval("sqrt(2)"))
    }

    @Test fun percentAndFunctions() {
        assertEquals("0.5", eval("50%"))
        assertEquals("30", eval("20% * 150"))
        assertEquals("5", eval("abs(-5)"))
        assertEquals("4", eval("sqrt(16)"))
    }

    @Test fun unicodeOperatorsAreAccepted() {
        assertEquals("12", eval("3 × 4"))
        assertEquals("5", eval("20 ÷ 4"))
        assertEquals("6", eval("10 − 4"))
    }

    @Test fun errorsAreExplicit() {
        assertEquals("ERR:Division by zero is undefined.", eval("8 / 0"))
        assertEquals("ERR:Division by zero is undefined.", eval("0 ^ -1"))
        assertTrue(eval("(1 + 2").startsWith("ERR:"))
        assertTrue(eval("2 +").startsWith("ERR:"))
        assertTrue(eval("1..2 + 3").startsWith("ERR:"))
        assertTrue(eval("sqrt(-1)").startsWith("ERR:"))
        assertTrue(eval("foo(2)").startsWith("ERR:"))
        assertTrue(eval("(-8) ^ 0.5").startsWith("ERR:"))
        assertTrue(eval("").startsWith("ERR:"))
    }

    @Test fun resourceLimitsPreventHangs() {
        assertTrue(eval("9 ^ 99999").startsWith("ERR:"))
        assertTrue(eval("9 ^ 9 ^ 9").startsWith("ERR:"))
        assertTrue(eval("(".repeat(100) + "1" + ")".repeat(100)).startsWith("ERR:"))
        assertTrue(eval("1+".repeat(150) + "1").startsWith("ERR:"))
        assertFalse(eval("2 ^ 1000").startsWith("ERR:"))
    }
}
