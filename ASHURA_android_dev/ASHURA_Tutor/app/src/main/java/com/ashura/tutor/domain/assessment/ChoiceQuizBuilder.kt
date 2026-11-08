package com.ashura.tutor.domain.assessment

import com.ashura.tutor.domain.library.QuizBuilder
import com.ashura.tutor.domain.library.TextChunk
import kotlin.random.Random

/** One imported note (or one passage group) that a test may draw questions from. */
data class QuizSource(val title: String, val chunks: List<TextChunk>)

/**
 * One four-option question. [correctIndex] always points at an option; the other three are
 * definitions or terms taken from the same body of notes, never invented text.
 */
data class ChoiceQuestion(
    val id: String,
    val prompt: String,
    val options: List<String>,
    val correctIndex: Int,
    val explanation: String,
    val sourceTitle: String,
    val chunkOrdinal: Int
) {
    init {
        require(options.size == 4) { "A choice question must have exactly four options" }
        require(options.distinct().size == 4) { "Choice-question options must be distinct" }
        require(correctIndex in options.indices) { "correctIndex must point at an option" }
    }
}

/**
 * Builds deterministic multiple-choice tests from the learner's imported notes (spec §3.4 / §12.2).
 *
 * Two safe shapes are produced from each "X is Y" fact:
 *  - "Which option best defines X?" with other notes' definitions as distractors;
 *  - "Which term does this description match?" with other terms as distractors.
 *
 * No fill-in-the-blank and no free-text items are generated. If the notes cannot supply four
 * distinct choices the builder returns an empty list rather than a Guess with repeated or invented
 * options. Option order is seeded from the question text, so retaking the same content is stable
 * for tests while still spreading the correct answer across positions.
 */
object ChoiceQuizBuilder {
    private const val MAX_OPTION_CHARS = 190
    private const val MAX_DESCRIPTION_CHARS = 260

    fun build(sources: List<QuizSource>, max: Int): List<ChoiceQuestion> {
        if (max <= 0) return emptyList()
        val facts = ArrayList<Fact>()
        val seen = HashSet<String>()
        for (source in sources) {
            for (definition in QuizBuilder.termDefinitions(source.chunks)) {
                val key = normalize(definition.term) + "|" + normalize(definition.definition)
                if (seen.add(key)) facts += Fact(source.title, definition)
            }
        }
        val terms = facts.map { it.definition.term }
            .filter { it.length in 3..70 }
            .distinctBy(::normalize)
        val definitions = facts.map { it.definition.definition }
            .filter { it.length >= 15 }
            .distinctBy(::normalize)
        // Four options need four distinct candidates on each side.
        if (terms.size < 4 || definitions.size < 4) return emptyList()

        val perSource = LinkedHashMap<String, MutableList<Candidate>>()
        for (fact in facts) {
            val group = perSource.getOrPut(fact.sourceTitle) { ArrayList() }
            group += Candidate(fact, Kind.DEFINITION_OF_TERM)
            group += Candidate(fact, Kind.TERM_FOR_DESCRIPTION)
        }

        val out = ArrayList<ChoiceQuestion>(max)
        for (candidate in interleave(perSource.values.toList())) {
            if (out.size >= max) break
            out += candidate.toQuestion(terms, definitions, out.size) ?: continue
        }
        return out
    }

    private enum class Kind { DEFINITION_OF_TERM, TERM_FOR_DESCRIPTION }

    private data class Fact(val sourceTitle: String, val definition: com.ashura.tutor.domain.library.TermDefinition)

    private data class Candidate(val fact: Fact, val kind: Kind)

    private fun Candidate.toQuestion(
        terms: List<String>,
        definitions: List<String>,
        index: Int
    ): ChoiceQuestion? {
        val definition = fact.definition
        val correct: String
        val prompt: String
        val pool: List<String>
        when (kind) {
            Kind.DEFINITION_OF_TERM -> {
                correct = definition.definition
                prompt = "Which option best defines \"${definition.term}\"?"
                val termKey = normalize(definition.term)
                pool = definitions.filter {
                    val key = normalize(it)
                    key != normalize(correct) && !key.contains(termKey)
                }
            }
            Kind.TERM_FOR_DESCRIPTION -> {
                // A definition that repeats its own term makes the reverse question trivial.
                if (normalize(definition.definition).contains(normalize(definition.term))) return null
                correct = definition.term
                prompt = "Which term does this description match?\n\n" +
                    "\"${clip(definition.definition, MAX_DESCRIPTION_CHARS)}\""
                pool = terms.filter { normalize(it) != normalize(correct) }
            }
        }

        val clippedCorrect = clip(correct, MAX_OPTION_CHARS)
        if (clippedCorrect.length < 3) return null
        val correctKey = normalize(clippedCorrect)
        val seed = (prompt + "|" + correctKey).hashCode()
        val random = Random(seed)

        // Shuffle deterministically, clip, then keep only distinct options. Clipping can make two
        // long definitions identical, so de-duplicating after clipping is required.
        val distractors = ArrayList<String>(3)
        val used = HashSet<String>()
        used += correctKey
        for (raw in pool.shuffled(random)) {
            val option = clip(raw, MAX_OPTION_CHARS)
            val key = normalize(option)
            if (option.length < 3 || key == correctKey || !used.add(key)) continue
            distractors += option
            if (distractors.size == 3) break
        }
        if (distractors.size < 3) return null

        val options = (distractors + clippedCorrect).shuffled(random)
        return ChoiceQuestion(
            id = "test-$index-${seed.toUInt()}",
            prompt = prompt,
            options = options,
            correctIndex = options.indexOf(clippedCorrect),
            explanation = "From \"${fact.sourceTitle}\": \"${definition.sentence}\"",
            sourceTitle = fact.sourceTitle,
            chunkOrdinal = definition.chunkOrdinal
        )
    }

    /** Round-robin across notes so one long note cannot dominate a library-wide test. */
    private fun interleave(groups: List<List<Candidate>>): List<Candidate> {
        val out = ArrayList<Candidate>()
        var round = 0
        while (true) {
            var added = false
            for (group in groups) {
                val candidate = group.getOrNull(round) ?: continue
                out += candidate
                added = true
            }
            if (!added) break
            round++
        }
        return out
    }

    private fun clip(text: String, max: Int): String {
        val trimmed = text.trim().trimEnd('.', ';', ':')
        if (trimmed.length <= max) return trimmed
        val cut = trimmed.take(max)
        val lastSpace = cut.lastIndexOf(' ')
        val body = if (lastSpace > max / 2) cut.take(lastSpace) else cut
        return body.trimEnd() + "…"
    }

    private fun normalize(text: String): String =
        text.lowercase().replace(Regex("[^\\p{L}\\p{M}0-9]+"), " ").trim()
}
