package com.ashura.tutor.domain.runtime

/**
 * Removes prompt-instruction leakage from model output. Small models sometimes copy the wording of
 * their own system prompt instead of following it: they emit placeholders such as `[n]` or `[Ref]`,
 * the phrase “using its id”, or an invented `EVIDENCE:` block with a fake source. None of that is a
 * real citation, so it must never reach the learner (spec §12.4, §13.2).
 *
 * Real numeric citations such as `[1]` and `[2]` are kept: those correspond to retrieved passages.
 */
object AnswerSanitizer {

    /** `[n]`, `[N]`, `[Ref]`, `[Reference]`, with optional spaces. */
    private val placeholder = Regex("""\[\s*(?:ref(?:erence)?|n)\s*]""", RegexOption.IGNORE_CASE)

    /** Hidden chain-of-thought blocks some models emit before the actual answer. */
    private val thinkingBlock = Regex(
        """(?is)<think(?:ing)?>.*?</think(?:ing)?>|<\|thinking\|>.*?<\|/thinking\|>""",
    )

    /** Chat-template control tokens must never be shown even when the runtime leaks them. */
    private val controlToken = Regex("""<\|[^|>]{1,40}\|>""")

    /** The prompt phrase that the model likes to parrot: “using its id”. */
    private val usingItsId = Regex("""\s*(?:using|with)\s+its\s+id\b""", RegexOption.IGNORE_CASE)

    /** Prompt-only provenance wording, e.g. “from a trusted source:”. */
    private val trustedSource = Regex("""\s*from\s+(?:a\s+)?trusted\s+source\b\s*:?""", RegexOption.IGNORE_CASE)

    /** The other prompt phrase the model parrots: “using [n] as reference”. */
    private val usingAsReference = Regex(
        """\s*(?:using|as)\s+(?:a\s+)?reference\b\s*:?""",
        RegexOption.IGNORE_CASE
    )

    /** An invented evidence heading. Retrieved sources are shown by the app, not written by the model. */
    private val evidenceHeading = Regex(
        """^[ \t>*_]*EVIDENCE[ \t*_]*:?(.*)$""",
        setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE)
    )

    /** The next real section after a leaked evidence block. */
    private val structuralLabel = Regex("""^\s*\**\s*(?:ANSWER|STEPS|CHECK)\b""", RegexOption.IGNORE_CASE)

    /** A real section marker that continues on the same line as the leaked heading. */
    private val inlineLabel = Regex("""\b(?:ANSWER|STEPS|CHECK)\b\s*:""")

    /** Echoed uncertainty instruction such as “If unsure, say so.” */
    private val echoedUncertainty = Regex("""\bIf unsure,\s*(?:say so|answer that)\b\.?""", RegexOption.IGNORE_CASE)

    /** A visible chain-of-thought section that ends where the real answer begins. */
    private val reasoningHeading = Regex(
        """^[ \t>*_]*(?:THINKING PROCESS|REASONING|ANALYSIS)[ \t*_]*:.*?(?=\b(?:ANSWER|STEPS|CHECK)\b|\z)""",
        setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL)
    )

    /** Real numeric citations such as `[1]` that point at a retrieved passage. */
    private val numericCitation = Regex("""(?<![A-Za-z0-9_])\[(\d{1,2})]""")

    fun clean(answer: String, availableCitations: Int = Int.MAX_VALUE): String {
        var text = answer
        text = thinkingBlock.replace(text, "")
        text = controlToken.replace(text, "")
        text = reasoningHeading.replace(text, "")
        text = placeholder.replace(text, "")
        text = usingItsId.replace(text, "")
        text = trustedSource.replace(text, "")
        text = usingAsReference.replace(text, "")
        text = stripEvidenceSections(text)
        text = stripUnbackedCitations(text, availableCitations)
        text = echoedUncertainty.replace(text, "")
        return text.lines()
            .map { it.trimEnd() }
            .joinToString("\n")
            .replace(Regex("""[ \t]{2,}"""), " ")
            .replace(Regex("""\n{3,}"""), "\n\n")
            .trim()
    }

    /**
     * A small model sometimes invents `[3]` even when only two passages were retrieved. Those look
     * like real citations, so anything outside the available range is removed. `[1]`/`[2]` survive
     * when they correspond to actual notes (spec §12.4).
     */
    private fun stripUnbackedCitations(text: String, available: Int): String =
        numericCitation.replace(text) { match ->
            val index = match.groupValues[1].toIntOrNull() ?: return@replace ""
            if (index in 1..available) match.value else ""
        }

    /**
     * Drops a hallucinated `EVIDENCE:` block, including the quoted “source” lines under it, until the
     * next real section or a blank line. If the same line continues with `ANSWER:`/`STEPS:`/`CHECK:`,
     * that part is kept.
     */
    private fun stripEvidenceSections(text: String): String {
        val out = ArrayList<String>()
        var inEvidence = false
        for (line in text.lines()) {
            if (!inEvidence) {
                val heading = evidenceHeading.find(line)
                if (heading != null) {
                    val rest = heading.groupValues[1]
                    val label = inlineLabel.find(rest) ?: structuralLabel.find(rest)
                    if (label != null) out.add(rest.substring(label.range.first).trim())
                    inEvidence = true
                    continue
                }
                out.add(line)
            } else {
                when {
                    line.isBlank() -> inEvidence = false
                    structuralLabel.containsMatchIn(line) -> {
                        inEvidence = false
                        out.add(line)
                    }
                    // Otherwise this is part of the invented evidence block: drop it.
                }
            }
        }
        return out.joinToString("\n")
    }
}
