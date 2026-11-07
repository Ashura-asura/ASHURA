package com.ashura.tutor.domain

/**
 * Deterministic parser for the tutor's structured output (spec §1.3, §3.3). The model is asked for
 * `ANSWER:`, `STEPS:` and `CHECK:` markers, but small models do not always comply, so anything
 * unrecognised is kept as plain body text instead of being dropped.
 */
data class StructuredAnswer(
    val answer: String?,
    val preamble: String,
    val steps: List<String>,
    val check: String?
) {
    val isStructured: Boolean get() = answer != null || steps.isNotEmpty() || check != null

    companion object {
        private val marker = Regex(
            "(?im)^[ \\t]*\\*{0,2}(ANSWER|STEPS|CHECK)[ \\t]*\\*{0,2}[ \\t]*:[ \\t]*\\*{0,2}[ \\t]*"
        )
        private val listPrefix = Regex("^[ \\t]*(?:\\d+[.)]|[-*•])[ \\t]*")

        fun parse(raw: String): StructuredAnswer {
            val text = raw.replace("\r\n", "\n").trim()
            val matches = marker.findAll(text).toList()
            if (matches.isEmpty()) return StructuredAnswer(null, text, emptyList(), null)

            val sections = matches.mapIndexed { i, m ->
                val end = matches.getOrNull(i + 1)?.range?.first ?: text.length
                m.groupValues[1].uppercase() to text.substring(m.range.last + 1, end).trim()
            }
            val firstStart = matches.first().range.first
            val preamble = text.substring(0, firstStart).trim()
            val byName = sections.toMap()

            val answer = byName["ANSWER"]?.takeIf { it.isNotBlank() }
            val steps = byName["STEPS"]?.let(::parseSteps).orEmpty()
            val check = byName["CHECK"]?.takeIf { it.isNotBlank() }
            return StructuredAnswer(answer = answer, preamble = preamble, steps = steps, check = check)
        }

        private fun parseSteps(block: String): List<String> =
            block.lines()
                .map { it.replace(listPrefix, "").trim() }
                .filter { it.isNotEmpty() }
                .take(8)
    }
}
