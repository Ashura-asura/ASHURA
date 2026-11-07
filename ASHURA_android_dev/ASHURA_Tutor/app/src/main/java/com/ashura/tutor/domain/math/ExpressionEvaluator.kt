package com.ashura.tutor.domain.math

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

/** Result of evaluating an arithmetic expression. */
sealed interface EvalResult {
    /** [exact] is false when the value was rounded (non-terminating division, fractional powers, sqrt). */
    data class Value(val value: BigDecimal, val exact: Boolean) : EvalResult
    data class Error(val message: String) : EvalResult
}

/**
 * Deterministic arithmetic evaluator (spec §11.1).
 *
 * Grammar (standard precedence, `^` right-associative, unary minus binds looser than `^`):
 * ```
 * expr    := term (('+' | '-') term)*
 * term    := unary (('*' | '/') unary)*
 * unary   := ('-' | '+') unary | power
 * power   := postfix ('^' unary)?
 * postfix := primary '%'*
 * primary := number | '(' expr ')' | ('sqrt' | 'abs') '(' expr ')'
 * ```
 * All limits are bounded so a hostile or accidental input cannot hang the app.
 */
object ExpressionEvaluator {
    const val MAX_LENGTH = 200
    private const val MAX_DEPTH = 40
    private const val MAX_EXPONENT = 1_000
    private const val MAX_DIGITS = 5_000
    private val MC = MathContext(34, RoundingMode.HALF_EVEN)

    fun evaluate(input: String): EvalResult {
        val text = normalize(input)
        if (text.isBlank()) return EvalResult.Error("Enter an expression.")
        if (text.length > MAX_LENGTH) return EvalResult.Error("Expression is too long (max $MAX_LENGTH characters).")
        return try {
            val parser = Parser(text)
            val result = parser.parseAll()
            EvalResult.Value(result.value, result.exact)
        } catch (e: CalcException) {
            EvalResult.Error(e.message ?: "Calculation failed.")
        } catch (e: ArithmeticException) {
            EvalResult.Error(e.message ?: "Calculation failed.")
        }
    }

    /** Human-readable rendering: plain notation, no trailing zeros, ≈ when rounded. */
    fun format(value: BigDecimal, exact: Boolean): String {
        val shown = if (exact) value else value.round(MathContext(12, RoundingMode.HALF_EVEN))
        val plain = shown.stripTrailingZeros().let { if (it.signum() == 0) BigDecimal.ZERO else it }.toPlainString()
        return if (exact) plain else "≈ $plain"
    }

    /**
     * Portable square root (Android's `BigDecimal.sqrt` is API 33, minSdk is 26).
     * Newton's method seeded from a double estimate; converges to [mc] precision in a few steps.
     */
    private fun sqrt(value: BigDecimal, mc: MathContext): BigDecimal {
        if (value.signum() == 0) return BigDecimal.ZERO
        val two = BigDecimal(2)
        var x = BigDecimal.valueOf(Math.sqrt(value.toDouble()))
        if (x.signum() == 0) x = BigDecimal.ONE
        repeat(64) {
            val next = x.add(value.divide(x, mc), mc).divide(two, mc)
            if (next.compareTo(x) == 0) return next
            x = next
        }
        return x.round(mc)
    }

    internal fun normalize(raw: String): String = DigitNormalizer.toAscii(raw)
        .replace('×', '*').replace('÷', '/').replace('−', '-').replace('–', '-')
        .replace("**", "^").trim()

    private class CalcException(message: String) : RuntimeException(message)
    private data class Num(val value: BigDecimal, val exact: Boolean)

    private class Parser(private val s: String) {
        private var pos = 0
        private var depth = 0

        fun parseAll(): Num {
            val v = expr()
            skipWs()
            if (pos < s.length) throw CalcException("Unexpected '${s[pos]}' at position ${pos + 1}.")
            return v
        }

        private fun skipWs() { while (pos < s.length && s[pos].isWhitespace()) pos++ }
        private fun peek(): Char? { skipWs(); return s.getOrNull(pos) }
        private fun eat(c: Char): Boolean { if (peek() == c) { pos++; return true }; return false }

        private fun enter() { if (++depth > MAX_DEPTH) throw CalcException("Expression is nested too deeply.") }
        private fun leave() { depth-- }

        private fun expr(): Num {
            enter()
            var left = term()
            while (true) {
                left = when {
                    eat('+') -> { val r = term(); Num(left.value.add(r.value), left.exact && r.exact) }
                    eat('-') -> { val r = term(); Num(left.value.subtract(r.value), left.exact && r.exact) }
                    else -> { leave(); return left }
                }
            }
        }

        private fun term(): Num {
            var left = unary()
            while (true) {
                left = when {
                    eat('*') -> { val r = unary(); guard(Num(left.value.multiply(r.value), left.exact && r.exact)) }
                    eat('/') -> divide(left, unary())
                    else -> return left
                }
            }
        }

        private fun divide(a: Num, b: Num): Num {
            if (b.value.signum() == 0) throw CalcException("Division by zero is undefined.")
            return try {
                Num(a.value.divide(b.value), a.exact && b.exact)
            } catch (_: ArithmeticException) {
                Num(a.value.divide(b.value, MC), false)
            }
        }

        private fun unary(): Num {
            enter()
            try {
                return when {
                    eat('-') -> unary().let { Num(it.value.negate(), it.exact) }
                    eat('+') -> unary()
                    else -> power()
                }
            } finally { leave() }
        }

        private fun power(): Num {
            val base = postfix()
            if (!eat('^')) return base
            val exp = unary()
            return pow(base, exp)
        }

        private fun pow(base: Num, exp: Num): Num {
            val isInt = exp.value.stripTrailingZeros().scale() <= 0
            if (isInt) {
                val e = exp.value.toBigIntegerExact()
                if (e.abs() > java.math.BigInteger.valueOf(MAX_EXPONENT.toLong()))
                    throw CalcException("Exponent is too large (max $MAX_EXPONENT).")
                val n = e.toInt()
                if (base.value.signum() == 0 && n < 0) throw CalcException("Division by zero is undefined.")
                if (base.value.precision().toLong() * kotlin.math.abs(n) > MAX_DIGITS)
                    throw CalcException("Result is too large to compute.")
                val p = base.value.pow(kotlin.math.abs(n))
                return if (n >= 0) guard(Num(p, base.exact)) else divide(Num(BigDecimal.ONE, true), Num(p, base.exact))
            }
            if (base.value.signum() < 0) throw CalcException("A negative number cannot be raised to a fractional power.")
            val d = Math.pow(base.value.toDouble(), exp.value.toDouble())
            if (!d.isFinite()) throw CalcException("Result is not a finite number.")
            return Num(BigDecimal(d, MC), false)
        }

        private fun postfix(): Num {
            var v = primary()
            while (eat('%')) v = divide(v, Num(BigDecimal(100), true))
            return v
        }

        private fun primary(): Num {
            val c = peek() ?: throw CalcException("Expression ended unexpectedly.")
            return when {
                c == '(' -> {
                    pos++
                    val v = expr()
                    if (!eat(')')) throw CalcException("Missing closing parenthesis.")
                    v
                }
                c.isDigit() || c == '.' -> number()
                c.isLetter() -> function()
                else -> throw CalcException("Unexpected '$c' at position ${pos + 1}.")
            }
        }

        private fun number(): Num {
            val start = pos
            while (pos < s.length && (s[pos].isDigit() || s[pos] == '.')) pos++
            val token = s.substring(start, pos)
            if (token.count { it == '.' } > 1 || token == ".") throw CalcException("Malformed number '$token'.")
            if (token.length > 60) throw CalcException("Number is too long.")
            return Num(BigDecimal(token), true)
        }

        private fun function(): Num {
            val start = pos
            while (pos < s.length && s[pos].isLetter()) pos++
            val name = s.substring(start, pos).lowercase()
            if (name != "sqrt" && name != "abs") throw CalcException("Unknown function '$name'.")
            if (!eat('(')) throw CalcException("Expected '(' after $name.")
            val arg = expr()
            if (!eat(')')) throw CalcException("Missing closing parenthesis.")
            return when (name) {
                "abs" -> Num(arg.value.abs(), arg.exact)
                else -> {
                    if (arg.value.signum() < 0) throw CalcException("Square root of a negative number is not a real number.")
                    val root = sqrt(arg.value, MC)
                    val exactRoot = arg.exact && root.multiply(root).compareTo(arg.value) == 0
                    Num(root, exactRoot)
                }
            }
        }

        private fun guard(n: Num): Num {
            if (n.value.precision() > MAX_DIGITS) throw CalcException("Result is too large to compute.")
            return n
        }
    }
}
