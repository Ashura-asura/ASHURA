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

    /**
     * An invented evidence heading. Retrieved sources are shown by the app, not written by the
     * model, so the heading is removed. If the same line continues with a real structural label
     * (for example `ANSWER:`), that remainder is preserved.
     */
    private val evidenceHeading = Regex(
        """^[ \t>*_]*EVIDENCE[ \t*_]*(?::[^\n]*?(?=\b(?:ANSWER|STEPS|CHECK)\b|$)|$)""",
        setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE)
    )

    /** Echoed uncertainty instruction such as “If unsure, say so.” */
    private val echoedUncertainty = Regex("""\bIf unsure,\s*(?:say so|answer that)\b\.?""", RegexOption.IGNORE_CASE)

    /** A visible chain-of-thought section that ends where the real answer begins. */
    private val reasoningHeading = Regex(
        """^[ \t>*_]*(?:THINKING PROCESS|REASONING|ANALYSIS)[ \t*_]*:.*?(?=\b(?:ANSWER|STEPS|CHECK)\b|\z)""",
        setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL)
    )

    fun clean(answer: String): String {
        var text = answer
        text = thinkingBlock.replace(text, "")
        text = controlToken.replace(text, "")
        text = reasoningHeading.replace(text, "")
        text = placeholder.replace(text, "")
        text = usingItsId.replace(text, "")
        text = trustedSource.replace(text, "")
        text = usingAsReference.replace(text, "")
        text = evidenceHeading.replace(text, "")
        text = echoedUncertainty.replace(text, "")
        return text.lines()
            .map { it.trimEnd() }
            .joinToString("\n")
            .replace(Regex("""[ \t]{2,}"""), " ")
            .replace(Regex("""\n{3,}"""), "\n\n")
            .trim()
    }
}
