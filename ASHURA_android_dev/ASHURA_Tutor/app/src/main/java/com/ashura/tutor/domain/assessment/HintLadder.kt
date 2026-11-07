package com.ashura.tutor.domain.assessment

/** What the practice screen should offer next (spec §3.3: stuck detection, hint ladder, guaranteed reveal). */
enum class LadderStep {
    /** Learner has not struggled yet; nothing to add. */
    NONE,

    /** Learner looks stuck and unused hints remain: nudge towards the next hint. */
    SUGGEST_HINT,

    /** Every hint is used (or none exist) and the learner is still stuck: offer the worked solution. */
    OFFER_SOLUTION
}

object HintLadder {
    /** Wrong answers after which a learner is treated as stuck. */
    const val STUCK_AFTER_WRONG = 2

    fun nextStep(
        hintsAvailable: Int,
        hintsShown: Int,
        wrongAttempts: Int,
        solutionShown: Boolean,
        askedForAnswer: Boolean = false
    ): LadderStep {
        require(hintsAvailable >= 0 && hintsShown >= 0 && wrongAttempts >= 0)
        if (solutionShown) return LadderStep.NONE
        val hintsLeft = hintsShown < hintsAvailable
        // "Just tell me" is honoured: climb straight to the solution rather than withholding it forever.
        if (askedForAnswer) return LadderStep.OFFER_SOLUTION
        val stuck = wrongAttempts >= STUCK_AFTER_WRONG
        return when {
            wrongAttempts >= 1 && hintsLeft && hintsShown < wrongAttempts -> LadderStep.SUGGEST_HINT
            stuck && !hintsLeft -> LadderStep.OFFER_SOLUTION
            else -> LadderStep.NONE
        }
    }

    /** Heuristic for a chat message that asks to stop being guided and just get the answer. */
    fun asksForDirectAnswer(message: String): Boolean {
        val t = message.lowercase()
        return listOf(
            "just tell me", "just give me the answer", "give me the answer", "i give up", "stop asking",
            "tell me the answer", "full derivation", "complete derivation", "derive it fully", "derive fully",
            "full solution", "complete solution", "show me the derivation", "show the derivation",
            "show all steps", "show every step", "don't guide me", "dont guide me"
        ).any { it in t }
    }
}
