package com.ashura.tutor.domain.library

/** A fill-in-the-blank item derived deterministically from the learner's own note. */
data class ClozeItem(val prompt: String, val answer: String, val hint: String, val chunkOrdinal: Int)

/**
 * Builds simple recall questions from imported notes without a model (spec §12.2 retrieval practice).
 * Picks one key term per sentence (a longer, non-stopword that recurs in the note), blanks its single occurrence,
 * and spreads questions across passages. Deterministic and bounded. Quality is modest by design: the blank is
 * always a word that really appears in the learner's text, so the answer is verifiable.
 */
object ClozeGenerator {
    private const val BLANK = "______"
    private val stop = setOf(
        "about", "after", "again", "against", "because", "before", "being", "between", "could", "during", "every", "first",
        "other", "should", "their", "there", "these", "those", "through", "under", "until", "which", "while", "would", "where",
        "another", "however", "within", "without", "something", "different", "called", "because"
    )
    private val sentenceSplit = Regex("(?<=[.!?\u0964])\\s+")
    private val wordRegex = Regex("[\\p{L}\\p{M}]+")

    fun generate(chunks: List<TextChunk>, max: Int = 5): List<ClozeItem> {
        if (chunks.isEmpty() || max <= 0) return emptyList()
        val frequency = HashMap<String, Int>()
        for (c in chunks) for (m in wordRegex.findAll(c.text)) frequency.merge(m.value.lowercase(), 1, Int::plus)

        // candidates per chunk, best first
        val perChunk = chunks.map { chunk -> chunk.ordinal to candidates(chunk, frequency) }
        val out = ArrayList<ClozeItem>()
        val usedAnswers = HashSet<String>()
        var round = 0
        while (out.size < max && perChunk.any { round < it.second.size }) {
            for ((_, list) in perChunk) {
                if (out.size >= max) break
                val item = list.getOrNull(round) ?: continue
                if (usedAnswers.add(item.answer.lowercase())) out.add(item)
            }
            round++
        }
        return out
    }

    private fun candidates(chunk: TextChunk, freq: Map<String, Int>): List<ClozeItem> {
        val items = ArrayList<Pair<Int, ClozeItem>>()
        for (sentence in chunk.text.split(sentenceSplit)) {
            val s = sentence.trim()
            if (s.length !in 40..220) continue
            val words = wordRegex.findAll(s).toList()
            if (words.size < 6) continue
            var best: MatchResult? = null; var bestScore = -1
            for (w in words) {
                val lower = w.value.lowercase()
                val latin = w.value.all { it.code < 0x250 }
                if (lower in stop) continue
                if (w.value.length < (if (latin) 6 else 4)) continue
                if (words.count { it.value.equals(w.value, ignoreCase = true) } != 1) continue // ambiguous blank
                val score = (freq[lower] ?: 1).coerceAtMost(5) * 10 + w.value.length.coerceAtMost(14)
                if (score > bestScore) { bestScore = score; best = w }
            }
            val target = best ?: continue
            val prompt = s.substring(0, target.range.first) + BLANK + s.substring(target.range.last + 1)
            val hint = "Starts with \"${target.value.first()}\" and has ${target.value.length} letters."
            items.add(bestScore to ClozeItem(prompt, target.value, hint, chunk.ordinal))
        }
        return items.sortedByDescending { it.first }.map { it.second }
    }
}
