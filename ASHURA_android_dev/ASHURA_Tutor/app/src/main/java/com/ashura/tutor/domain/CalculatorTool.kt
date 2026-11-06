package com.ashura.tutor.domain

import kotlin.math.pow

/**
 * Deterministic calculator tool. Exact arithmetic is verified by computation,
 * not by the language model (spec §11.1). Supports +, -, *, /, ^ and
 * unit-free school arithmetic. Division by zero and non-finite results are
 * reported explicitly rather than silently approximated.
 */
class CalculatorTool : TaskController.Tool {

    override val name = "calculator"
    override val handles: (String) -> Boolean = { lower ->
        Regex("^[\\d\\s.+*/^()\\-]+$").matches(lower.trim()) &&
            lower.containsAny(listOf("+", "-", "*", "/", "^"))
    }

    override suspend fun execute(request: TutorRequest): TaskController.ToolResult {
        val raw = request.question.trim()
        val normalized = raw.replace("×", "*").replace("÷", "/")
        val match = Regex("^(-?\\d+(?:\\.\\d+)?)\\s*([+\\-*/^])\\s*(-?\\d+(?:\\.\\d+)?)$")
            .matchEntire(normalized) ?: return TaskController.ToolResult.Unhandled("Not a binary arithmetic expression.")

        val a = match.groupValues[1].toDouble()
        val op = match.groupValues[2]
        val b = match.groupValues[3].toDouble()

        val result = try {
            when (op) {
                "+" -> a + b
                "-" -> a - b
                "*" -> a * b
                "/" -> {
                    if (b == 0.0) throw ArithmeticException("Division by zero is undefined.")
                    a / b
                }
                "^" -> a.pow(b)
                else -> throw ArithmeticException("Unsupported operator $op.")
            }
        } catch (e: ArithmeticException) {
            return TaskController.ToolResult.Handled(e.message ?: "Calculation failed.", ResponseMode.DETERMINISTIC)
        }

        if (!result.isFinite()) {
            return TaskController.ToolResult.Handled("Result is not finite.", ResponseMode.DETERMINISTIC)
        }

        val formatted = if (result % 1.0 == 0.0) result.toLong().toString() else result.toString()
        return TaskController.ToolResult.Handled("$a $op $b = $formatted", ResponseMode.DETERMINISTIC)
    }
}

private fun String.containsAny(keywords: List<String>): Boolean = keywords.any { contains(it, ignoreCase = true) }
