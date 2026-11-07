package com.ashura.tutor.domain.library

import com.ashura.tutor.domain.ContextSnippet

/** A retrieved passage with provenance; independent of Room so the policy is testable on a JVM. */
data class PassageRef(val title: String, val ordinal: Int, val text: String)

data class GroundedContext(val snippets: List<ContextSnippet>, val citations: List<String>)

/**
 * Chooses which retrieved passages may enter the model prompt or the extractive answer (spec §10.3, §18.1).
 * Bounded count and size, at most [perSource] passages per document, near-duplicates removed, order preserved
 * (callers pass hits already ranked best-first).
 */
object GroundingPolicy {
    fun select(hits: List<PassageRef>, maxPassages: Int = 4, maxChars: Int = 3_000, perSource: Int = 2): GroundedContext {
        val seen = HashSet<String>()
        val perTitle = HashMap<String, Int>()
        val snippets = ArrayList<ContextSnippet>()
        var used = 0
        for (h in hits) {
            if (snippets.size >= maxPassages) break
            val text = h.text.trim()
            if (text.isEmpty()) continue
            val fingerprint = text.lowercase().filterNot(Char::isWhitespace).take(120)
            if (!seen.add(fingerprint)) continue
            if ((perTitle[h.title] ?: 0) >= perSource) continue
            if (used + text.length > maxChars) continue
            perTitle[h.title] = (perTitle[h.title] ?: 0) + 1
            used += text.length
            snippets.add(ContextSnippet(h.title, text, "${h.title} · passage ${h.ordinal + 1}"))
        }
        val citations = snippets.mapIndexed { i, s -> "[${i + 1}] ${s.sourceLabel}" }
        return GroundedContext(snippets, citations)
    }
}
