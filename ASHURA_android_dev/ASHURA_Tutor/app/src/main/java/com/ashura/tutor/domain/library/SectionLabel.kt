package com.ashura.tutor.domain.library

/**
 * Recovers the section label ("Page 3", "Slide 2", "Sheet: Marks") that document extractors put at the
 * start of a passage, so citations can say where in a document the evidence came from (spec Phase 7).
 * Only labels the extractors generate are accepted; a learner's own bracketed text is not treated as
 * provenance.
 */
object SectionLabel {
    private val marker = Regex("^\\[([^]\\n]{1,80})]\\s*$")
    private val known = listOf("Page ", "Slide ", "Sheet: ", "Notes", "Image")

    fun forChunk(text: String): String? {
        val firstLine = text.trimStart().lineSequence().firstOrNull()?.trim() ?: return null
        val label = marker.matchEntire(firstLine)?.groupValues?.get(1) ?: return null
        return label.takeIf { candidate -> known.any { candidate.startsWith(it) } }
    }

    /** Removes the provenance label line so quizzes and reading text do not show "[Page 3]" mid-sentence. */
    fun strip(text: String): String {
        val trimmed = text.trimStart()
        val firstLine = trimmed.lineSequence().firstOrNull()?.trim() ?: return text
        val label = marker.matchEntire(firstLine)?.groupValues?.get(1) ?: return text
        if (known.none { label.startsWith(it) }) return text
        return trimmed.removePrefix(firstLine).trimStart()
    }
}
