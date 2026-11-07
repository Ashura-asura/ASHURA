package com.ashura.tutor.data

/**
 * Turns free user text into a safe FTS5 MATCH expression: every alphanumeric token becomes a quoted
 * prefix term (letters, combining marks such as Devanagari vowel signs, and digits), all AND-ed. User text can therefore never inject FTS operators (NEAR, OR, column filters, quotes).
 */
object FtsQuery {
    private const val MAX_TOKENS = 12
    private const val MAX_TOKEN_LENGTH = 40

    fun build(userText: String): String? {
        val tokens = Regex("[\\p{L}\\p{M}\\p{N}]+").findAll(userText)
            .map { it.value.take(MAX_TOKEN_LENGTH).lowercase() }
            .take(MAX_TOKENS).toList()
        if (tokens.isEmpty()) return null
        return tokens.joinToString(" ") { "\"$it\"*" }
    }

    private val stopwords = setOf(
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "of", "in", "on", "at", "to", "for",
        "from", "by", "with", "about", "as", "and", "or", "not", "no", "it", "its", "this", "that", "these", "those", "what", "which",
        "who", "whom", "whose", "when", "where", "why", "how", "can", "could", "should", "would", "will", "shall", "may", "might",
        "me", "my", "i", "you", "your", "we", "our", "they", "their", "he", "she", "his", "her", "please", "explain", "tell", "say",
        "says", "give", "show", "mean", "means", "define", "describe", "if", "then", "so", "than", "into", "there", "have", "has", "had"
    )
    private const val MAX_QUESTION_TOKENS = 8

    /** Distinctive search words from a natural-language question (stopwords removed, de-duplicated, bounded). */
    fun keywords(question: String): List<String> =
        Regex("[\\p{L}\\p{M}\\p{N}]+").findAll(question)
            .map { it.value.take(MAX_TOKEN_LENGTH).lowercase() }
            .filter { it !in stopwords && (it.length >= 3 || it.any { c -> !c.isLetter() || c.code > 127 }) }
            .distinct().take(MAX_QUESTION_TOKENS).toList()

    /**
     * FTS5 expression for a question: keywords OR-ed (BM25 ranks passages matching more words higher).
     * Returns null when the question has no distinctive words. Same injection-safe quoting as [build].
     */
    fun forQuestion(question: String): String? {
        val words = keywords(question)
        if (words.isEmpty()) return null
        return words.joinToString(" OR ") { "\"$it\"*" }
    }
}
