package com.ashura.tutor.domain.text

/**
 * A small, dependency-free LaTeX-to-Unicode formatter for model answers.
 *
 * The app does not bundle a maths typesetting engine, and a WebView/MathJax download would break the
 * offline-first constraint. Instead this converts the common notation a tutor model emits into
 * readable Unicode: `\frac`, `\sqrt`, Greek letters, operators, accents, superscripts and
 * subscripts. Unsupported commands lose only the backslash, never the surrounding text.
 */
object LatexLite {

    private val displayMath = Regex("""\$\$(.+?)\$\$""", setOf(RegexOption.DOT_MATCHES_ALL))
    private val inlineMath = Regex("""\$(.+?)\$""", setOf(RegexOption.DOT_MATCHES_ALL))
    private val bracketMath = Regex("""\\\[(.+?)\\\]""", setOf(RegexOption.DOT_MATCHES_ALL))
    private val parenMath = Regex("""\\\((.+?)\\\)""", setOf(RegexOption.DOT_MATCHES_ALL))

    private val fraction = Regex("""\\(?:d|t)?frac\{([^{}]*)\}\{([^{}]*)\}""")
    private val sqrt = Regex("""\\sqrt\{([^{}]*)\}""")
    private val wrapper = Regex(
        """\\(?:text|textrm|mathrm|mathbf|mathit|mathsf|mathtt|mathcal|mathbb|operatorname|textbf|textit)\{([^{}]*)\}"""
    )
    private val accent = Regex("""\\(dot|ddot|hat|bar|vec|tilde)\{([^{}])\}""")
    private val environment = Regex("""\\(?:begin|end)\{[^{}]*}""")
    private val command = Regex("""\\([A-Za-z]+)""")
    private val lineBreak = Regex("""\\\\(\[[^\]]*])?""")
    private val spacing = Regex("""\\(?:,|;|!|quad|qquad|thinspace|medspace|thickspace)""")
    private val superscript = Regex("""\^(\{[^{}]*}|.)""")
    private val subscript = Regex("""_(\{[^{}]*}|.)""")

    private val symbols = mapOf(
        "cdot" to "·", "times" to "×", "div" to "÷", "pm" to "±", "mp" to "∓",
        "approx" to "≈", "neq" to "≠", "ne" to "≠", "leq" to "≤", "le" to "≤",
        "geq" to "≥", "ge" to "≥", "ll" to "≪", "gg" to "≫", "equiv" to "≡",
        "propto" to "∝", "infty" to "∞", "partial" to "∂", "nabla" to "∇",
        "int" to "∫", "iint" to "∬", "iiint" to "∭", "oint" to "∮",
        "sum" to "∑", "prod" to "∏", "to" to "→", "rightarrow" to "→",
        "leftarrow" to "←", "leftrightarrow" to "↔", "Rightarrow" to "⇒",
        "Leftarrow" to "⇐", "Leftrightarrow" to "⇔", "mapsto" to "↦",
        "in" to "∈", "notin" to "∉", "subset" to "⊂", "subseteq" to "⊆",
        "supset" to "⊃", "supseteq" to "⊇", "cup" to "∪", "cap" to "∩",
        "emptyset" to "∅", "forall" to "∀", "exists" to "∃", "neg" to "¬",
        "land" to "∧", "lor" to "∨", "angle" to "∠", "degree" to "°",
        "perp" to "⊥", "parallel" to "∥", "sim" to "∼", "simeq" to "≃",
        "cong" to "≅", "prime" to "′", "ldots" to "…", "dots" to "…", "cdots" to "⋯",
        "alpha" to "α", "beta" to "β", "gamma" to "γ", "delta" to "δ",
        "epsilon" to "ε", "varepsilon" to "ε", "zeta" to "ζ", "eta" to "η",
        "theta" to "θ", "vartheta" to "ϑ", "iota" to "ι", "kappa" to "κ",
        "lambda" to "λ", "mu" to "μ", "nu" to "ν", "xi" to "ξ", "omicron" to "ο",
        "pi" to "π", "varpi" to "ϖ", "rho" to "ρ", "varrho" to "ϱ",
        "sigma" to "σ", "varsigma" to "ς", "tau" to "τ", "upsilon" to "υ",
        "phi" to "φ", "varphi" to "φ", "chi" to "χ", "psi" to "ψ", "omega" to "ω",
        "Gamma" to "Γ", "Delta" to "Δ", "Theta" to "Θ", "Lambda" to "Λ",
        "Xi" to "Ξ", "Pi" to "Π", "Sigma" to "Σ", "Upsilon" to "Υ",
        "Phi" to "Φ", "Psi" to "Ψ", "Omega" to "Ω"
    )

    private val accentMarks = mapOf(
        "dot" to "\u0307", "ddot" to "\u0308", "hat" to "\u0302",
        "bar" to "\u0304", "vec" to "\u20D7", "tilde" to "\u0303"
    )

    private val superscripts = mapOf(
        '0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴', '5' to '⁵',
        '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹', '+' to '⁺', '-' to '⁻',
        '=' to '⁼', '(' to '⁽', ')' to '⁾', 'n' to 'ⁿ', 'i' to 'ⁱ',
        'a' to 'ᵃ', 'b' to 'ᵇ', 'c' to 'ᶜ', 'd' to 'ᵈ', 'e' to 'ᵉ', 'f' to 'ᶠ',
        'g' to 'ᵍ', 'h' to 'ʰ', 'j' to 'ʲ', 'k' to 'ᵏ', 'l' to 'ˡ', 'm' to 'ᵐ',
        'o' to 'ᵒ', 'p' to 'ᵖ', 'r' to 'ʳ', 's' to 'ˢ', 't' to 'ᵗ', 'u' to 'ᵘ',
        'v' to 'ᵛ', 'w' to 'ʷ', 'x' to 'ˣ', 'y' to 'ʸ', 'z' to 'ᶻ'
    )

    private val subscripts = mapOf(
        '0' to '₀', '1' to '₁', '2' to '₂', '3' to '₃', '4' to '₄', '5' to '₅',
        '6' to '₆', '7' to '₇', '8' to '₈', '9' to '₉', '+' to '₊', '-' to '₋',
        '=' to '₌', '(' to '₍', ')' to '₎', 'a' to 'ₐ', 'e' to 'ₑ', 'h' to 'ₕ',
        'i' to 'ᵢ', 'j' to 'ⱼ', 'k' to 'ₖ', 'l' to 'ₗ', 'm' to 'ₘ', 'n' to 'ₙ',
        'o' to 'ₒ', 'p' to 'ₚ', 'r' to 'ᵣ', 's' to 'ₛ', 't' to 'ₜ', 'u' to 'ᵤ',
        'v' to 'ᵥ', 'x' to 'ₓ'
    )

    fun render(raw: String): String {
        if (raw.indexOf('\\') < 0 && raw.indexOf('$') < 0) return raw
        var text = raw.replace("\r\n", "\n")
        text = displayMath.replace(text) { "\n" + it.groupValues[1].trim() + "\n" }
        text = bracketMath.replace(text) { "\n" + it.groupValues[1].trim() + "\n" }
        text = parenMath.replace(text) { it.groupValues[1] }
        text = inlineMath.replace(text) { it.groupValues[1] }

        // Roots first so a fraction whose numerator contains \sqrt{...} can then be matched.
        text = sqrt.replace(text) { "√(${it.groupValues[1]})" }
        repeat(6) {
            text = fraction.replace(text) { "(${it.groupValues[1]})/(${it.groupValues[2]})" }
        }
        text = wrapper.replace(text) { it.groupValues[1] }
        text = accent.replace(text) { m ->
            val base = m.groupValues[2]
            base + accentMarks.getValue(m.groupValues[1])
        }
        // Prefer precomposed letters where Unicode provides them, so selection and copy stay clean.
        text = text.replace("x\u0308", "ẍ").replace("x\u0307", "ẋ")
            .replace("X\u0308", "Ẍ").replace("X\u0307", "Ẋ")
        text = environment.replace(text, "\n")
        text = lineBreak.replace(text, "\n")
        text = spacing.replace(text, " ")
        text = text.replace("\\left", "").replace("\\right", "")
        text = text.replace("&", " ")
        text = command.replace(text) { m -> symbols[m.groupValues[1]] ?: m.groupValues[1] }

        text = superscript.replace(text) { m ->
            val body = m.groupValues[1].removeSurrounding("{", "}")
            unicodeOrFallback(body, superscripts, "^")
        }
        text = subscript.replace(text) { m ->
            val body = m.groupValues[1].removeSurrounding("{", "}")
            unicodeOrFallback(body, subscripts, "_")
        }

        return text.lines().joinToString("\n") { it.trimEnd() }
            .replace(Regex("""[ \t]{2,}"""), " ")
            .replace(Regex("""\n{3,}"""), "\n\n")
            .trim()
    }

    private fun unicodeOrFallback(body: String, table: Map<Char, Char>, marker: String): String {
        if (body.isEmpty()) return ""
        val converted = StringBuilder()
        for (c in body) {
            val mapped = table[c] ?: return if (body.all { it.isLetterOrDigit() }) marker + body else "$marker($body)"
            converted.append(mapped)
        }
        return converted.toString()
    }
}
