package com.ashura.tutor.domain.library

/** What kind of retrieval-practice item a note produced. */
enum class QuizKind { CLOZE, DEFINITION, EXPLANATION }

/**
 * One practice item built from a learner's imported document. Cloze items are machine-checkable;
 * definition and explanation items are self-assessed because free text has many valid phrasings.
 */
data class QuizItem(
    val kind: QuizKind,
    val prompt: String,
    val answer: String,
    val selfAssessed: Boolean,
    val hint: String? = null,
    val explanation: String? = null,
    val section: String? = null,
    val chunkOrdinal: Int
)

/** One "X is Y" fact extracted from a note; used to build four-option concept questions. */
data class TermDefinition(
    val term: String,
    val definition: String,
    val sentence: String,
    val section: String?,
    val chunkOrdinal: Int
)

/**
 * Builds a mixed retrieval-practice set from an imported note without a model (spec §12.2).
 *
 * The default set is deliberately varied rather than a wall of fill-in-the-blanks: up to twelve
 * cloze items (machine-checked) plus up to eight definition/explanation items (self-assessed), with
 * questions spread across pages, slides and sheets. Every answer is traceable to the learner's own
 * text, so nothing is invented and the quiz still works when no model is loaded.
 */
object QuizBuilder {
    const val DEFAULT_MAX = 20
    const val MAX_CLOZE = 12
    const val MAX_DEFINITIONS = 6

    private val sentenceSplit = Regex("(?<=[.!?\u0964])\\s+")
    private val markerLine = Regex("^\\[[^]\\n]{1,80}]$")
    private val headingJunk = Regex("^[#>*\\-–—\\s]+")
    private val whitespace = Regex("\\s+")
    private val nonWord = Regex("[^\\p{L}\\p{M}0-9]+")
    private val wordRegex = Regex("[\\p{L}\\p{M}][\\p{L}\\p{M}'’\\-]*")

    private val badTerms = setOf(
        "it", "this", "that", "there", "these", "those", "they", "we", "you", "he", "she",
        "which", "what", "who", "one", "some", "many", "most", "all", "each", "such", "here",
        "the", "a", "an", "and", "but", "or", "if", "then", "when", "where", "why", "how",
        "however", "therefore", "also", "both", "other", "another"
    )

    /** Single words that are too vague to make a good "explain this" prompt. */
    private val genericSingleWords = setOf(
        "reaction", "reactions", "molecule", "molecules", "process", "processes", "energy",
        "thing", "things", "part", "parts", "type", "types", "example", "examples", "change",
        "changes", "number", "numbers", "amount", "amounts", "result", "results", "value",
        "values", "system", "systems", "method", "methods", "form", "forms", "case", "cases",
        "point", "points", "level", "levels", "effect", "effects", "factor", "factors",
        "activity", "activities", "feature", "features", "important", "different", "various",
        "several", "common", "general", "possible", "necessary"
    )
    private val adjectiveSuffixes = listOf(
        "-bound", "-like", "-based", "-dependent", "-independent", "-specific", "-related", "-driven"
    )
    private val verbs = setOf(
        "is", "are", "was", "were", "has", "have", "had", "does", "do", "did", "can", "could",
        "will", "would", "should", "must", "may", "might", "contains", "contain", "produces",
        "produce", "converts", "convert", "releases", "release", "absorbs", "absorb", "speeds",
        "speed", "affects", "affect", "carries", "carry", "takes", "take", "makes", "make",
        "uses", "use", "allows", "allow", "helps", "help", "forms", "form", "means", "refers",
        "describes", "represents", "denotes", "includes", "include", "consists", "causes", "cause",
        "happens", "occur", "occurs", "requires", "require", "provides", "provide", "stores",
        "store", "breaks", "break", "gives", "give", "needs", "need"
    )

    // Most specific patterns first: "X is defined as Y", "X means Y", "X is a Y", "X is Y".
    private val definitionPatterns = listOf(
        Regex("^(.{3,70}?)\\s+(?:is|are|was|were)\\s+(?:defined|known)\\s+as\\s+(.{15,320})$", RegexOption.IGNORE_CASE),
        Regex("^(.{3,70}?)\\s+(?:is|are|was|were)\\s+called\\s+(.{15,320})$", RegexOption.IGNORE_CASE),
        Regex("^(.{3,70}?)\\s+(?:refers\\s+to|means|describes|represents|denotes)\\s+(.{15,320})$", RegexOption.IGNORE_CASE),
        Regex("^(.{3,70}?)\\s+(?:is|are)\\s+(?:a|an|the)\\s+(.{15,320})$", RegexOption.IGNORE_CASE),
        Regex("^(.{3,70}?)\\s+(?:is|are)\\s+(.{15,320})$", RegexOption.IGNORE_CASE)
    )

    fun build(chunks: List<TextChunk>, title: String, max: Int = DEFAULT_MAX): List<QuizItem> {
        if (chunks.isEmpty() || max <= 0) return emptyList()
        val ordered = chunks.sortedBy { it.ordinal }
        val sections = ordered.associate { it.ordinal to SectionLabel.forChunk(it.text) }
        // Keep "[Page 3]" as provenance, not as part of a quiz sentence.
        val body = ordered.map { it.copy(text = SectionLabel.strip(it.text)) }

        val cloze = clozeItems(body, sections, title, minOf(max, MAX_CLOZE))
        val definitionTerms = HashSet<String>()
        val definitions = definitionItems(
            body, sections, title, definitionTerms, minOf(max - cloze.size, MAX_DEFINITIONS)
        )
        val explanations = explanationItems(
            body, sections, title, definitionTerms,
            (max - cloze.size - definitions.size).coerceAtLeast(0)
        )

        return interleave(listOf(cloze, definitions, explanations), max)
    }

    /**
     * Every "X is Y" fact found in [chunks], in passage order. Four-option tests use these
     * definitions as both the prompt and the answer pool, so a multiple-choice question never
     * invents content that is not already in the learner's own notes.
     */
    fun termDefinitions(chunks: List<TextChunk>): List<TermDefinition> {
        if (chunks.isEmpty()) return emptyList()
        return chunks.sortedBy { it.ordinal }.flatMap { chunk ->
            val section = SectionLabel.forChunk(chunk.text)
            candidateSentences(SectionLabel.strip(chunk.text)).mapNotNull { sentence ->
                definitionOf(sentence)?.let {
                    TermDefinition(it.term, it.definition, sentence, section, chunk.ordinal)
                }
            }
        }
    }

    private fun clozeItems(
        chunks: List<TextChunk>,
        sections: Map<Int, String?>,
        title: String,
        max: Int
    ): List<QuizItem> = ClozeGenerator.generate(chunks, max).map { item ->
        val section = sections[item.chunkOrdinal]
        QuizItem(
            kind = QuizKind.CLOZE,
            prompt = "Fill in the blank (${where(title, section)}): ${item.prompt}",
            answer = item.answer,
            selfAssessed = false,
            hint = item.hint,
            explanation = "From \"$title\"${sectionSuffix(section)}, passage ${item.chunkOrdinal + 1}.",
            section = section,
            chunkOrdinal = item.chunkOrdinal
        )
    }

    private fun definitionItems(
        chunks: List<TextChunk>,
        sections: Map<Int, String?>,
        title: String,
        terms: MutableSet<String>,
        max: Int
    ): List<QuizItem> {
        if (max <= 0) return emptyList()
        val perChunk = chunks.map { chunk ->
            chunk to candidateSentences(chunk.text).mapNotNull(::definitionOf)
        }
        val out = ArrayList<QuizItem>(max)
        var round = 0
        while (out.size < max && perChunk.any { round < it.second.size }) {
            for ((chunk, candidates) in perChunk) {
                if (out.size >= max) break
                val candidate = candidates.getOrNull(round) ?: continue
                if (!terms.add(normalize(candidate.term))) continue
                val section = sections[chunk.ordinal]
                val place = section?.let { " ($it)" } ?: ""
                out.add(
                    QuizItem(
                        kind = QuizKind.DEFINITION,
                        prompt = "In your own words, define \"${candidate.term}\"$place.",
                        answer = candidate.definition,
                        selfAssessed = true,
                        hint = "Say what \"${candidate.term}\" is, then why it matters.",
                        explanation = "From \"$title\"${sectionSuffix(section)}: \"${candidate.sentence}\"",
                        section = section,
                        chunkOrdinal = chunk.ordinal
                    )
                )
            }
            round++
        }
        return out
    }

    private fun explanationItems(
        chunks: List<TextChunk>,
        sections: Map<Int, String?>,
        title: String,
        exclude: Set<String>,
        max: Int
    ): List<QuizItem> {
        if (max <= 0) return emptyList()
        val perChunk = chunks.map { chunk -> chunk to topicCandidates(chunk.text) }
        val out = ArrayList<QuizItem>(max)
        val topics = HashSet<String>()
        var round = 0
        while (out.size < max && perChunk.any { round < it.second.size }) {
            for ((chunk, candidates) in perChunk) {
                if (out.size >= max) break
                val candidate = candidates.getOrNull(round) ?: continue
                val key = normalize(candidate.topic)
                if (key in exclude || !topics.add(key)) continue
                val section = sections[chunk.ordinal]
                val place = section?.let { " ($it)" } ?: ""
                out.add(
                    QuizItem(
                        kind = QuizKind.EXPLANATION,
                        prompt = "Explain in your own words: \"${candidate.topic}\"$place.",
                        answer = candidate.modelAnswer,
                        selfAssessed = true,
                        hint = "Cover the idea, why it matters, and one example from the text.",
                        explanation = "From \"$title\"${sectionSuffix(section)}: \"${candidate.sentence}\"",
                        section = section,
                        chunkOrdinal = chunk.ordinal
                    )
                )
            }
            round++
        }
        return out
    }

    /** Mixes the categories so the quiz does not feel like one repeated exercise. */
    private fun interleave(groups: List<List<QuizItem>>, max: Int): List<QuizItem> {
        val out = ArrayList<QuizItem>(max)
        val seen = HashSet<String>()
        var round = 0
        while (out.size < max && groups.any { round < it.size }) {
            for (group in groups) {
                if (out.size >= max) break
                val item = group.getOrNull(round) ?: continue
                val key = item.kind.name + "|" + normalize(item.prompt)
                if (seen.add(key)) out.add(item)
            }
            round++
        }
        return out
    }

    private data class Definition(val term: String, val definition: String, val sentence: String)
    private data class Topic(val topic: String, val modelAnswer: String, val sentence: String)

    private fun candidateSentences(text: String): List<String> =
        text.split(sentenceSplit).map { it.trim() }.filter { it.length in 30..360 }

    private fun definitionOf(sentence: String): Definition? {
        if (sentence.startsWith("[")) return null
        for (pattern in definitionPatterns) {
            val match = pattern.find(sentence) ?: continue
            val term = cleanTerm(match.groupValues[1]) ?: continue
            val definition = match.groupValues[2].trim().trimEnd('.', ';', ':')
            if (definition.length < 15) continue
            if (match.groupValues[1].contains('?')) continue
            return Definition(term, definition, sentence)
        }
        return null
    }

    private fun cleanTerm(raw: String): String? {
        var term = raw.trim().trim('"', '\'', '(', ')', ',', ';', ':').trim()
        term = term.replace(Regex("^(?:the|a|an)\\s+", RegexOption.IGNORE_CASE), "").trim()
        if (term.length !in 3..70) return null
        if (term.any { it == '\n' || it == '[' || it == ']' || it == '?' || it == '!' }) return null
        if (term.any { it.isDigit() }) return null
        val words = term.split(whitespace).filter { it.isNotBlank() }
        if (words.isEmpty() || words.size > 7) return null
        if (words.first().lowercase() in badTerms) return null
        return term
    }

    private fun topicCandidates(text: String): List<Topic> {
        val sentences = text.split(sentenceSplit).map { it.trim() }.filter { it.length >= 25 }
        if (sentences.isEmpty()) return emptyList()
        val body = sentences.take(3).joinToString(" ").take(520)
        val out = ArrayList<Topic>()

        // Headings and short label lines make the best "explain this idea" prompts.
        text.lines().asSequence().map { it.trim() }.filter { it.isNotEmpty() }.take(5).forEach { line ->
            headingOf(line)?.let { out.add(Topic(it, body, line)) }
        }
        // The subject of a sentence names a concept worth explaining in the learner's own words.
        for (sentence in sentences) {
            subjectPhrase(sentence)?.let { out.add(Topic(it, sentence, sentence)) }
        }
        // Explicit definitions not already surfaced as a subject.
        for (sentence in sentences) {
            definitionOf(sentence)?.let { out.add(Topic(it.term, sentence, sentence)) }
        }
        // Last resort for short or label-like passages.
        for (sentence in sentences) {
            keyPhrase(sentence)?.let { out.add(Topic(it, sentence, sentence)) }
        }
        return out.distinctBy { normalize(it.topic) }
    }

    private fun subjectPhrase(sentence: String): String? {
        val words = wordRegex.findAll(sentence).map { it.value }.toList()
        if (words.size < 2) return null
        val firstVerb = words.indexOfFirst { it.lowercase() in verbs }
        if (firstVerb < 1) return null
        val subject = words.subList(maxOf(0, firstVerb - 5), firstVerb).joinToString(" ")
        return cleanTerm(subject)
    }

    private fun headingOf(line: String): String? {
        val cleaned = line.replace(headingJunk, "").trim()
        if (cleaned.length !in 4..80) return null
        if (markerLine.matches(cleaned)) return null
        if (cleaned.endsWith('.') || cleaned.endsWith('!') || cleaned.endsWith('?') || cleaned.endsWith(':')) return null
        if (cleaned.count { it.isLetter() } < 4) return null
        if (cleaned.split(whitespace).size > 10) return null
        return cleaned
    }

    private fun keyPhrase(sentence: String): String? {
        val candidates = wordRegex.findAll(sentence).map { it.value }
            .filter { it.length >= 5 }
            .filter { it.lowercase() !in badTerms && it.lowercase() !in genericSingleWords }
            .filterNot { word -> word.contains('-') && adjectiveSuffixes.any { word.lowercase().endsWith(it) } }
            .filterNot { word -> word.lowercase().endsWith("ing") || word.lowercase().endsWith("ed") }
            .toList()
        return candidates.maxWithOrNull(
            compareBy<String> { it.first().isUpperCase() }.thenBy { it.length }
        )?.take(40)
    }

    private fun where(title: String, section: String?): String =
        if (section == null) "from \"$title\"" else "from \"$title\", $section"

    private fun sectionSuffix(section: String?): String = section?.let { ", $it" } ?: ""

    private fun normalize(text: String): String =
        text.lowercase().replace(nonWord, " ").trim()
}
