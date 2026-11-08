package com.ashura.tutor.domain.assessment

/**
 * The three timed test lengths the learner can choose (spec §3.4 / §21).
 *
 * The timer is selected automatically from the mode: every question gets the same budget, so
 * Quick lasts 20 minutes, Medium 35 minutes and Long 50 minutes. Keeping the rule in one place
 * means the UI, the session and the result history can never disagree about a test's length.
 */
enum class TestMode(val questionCount: Int, val secondsPerQuestion: Int) {
    QUICK(20, 60),
    MEDIUM(35, 60),
    LONG(50, 60);

    val durationSeconds: Int get() = questionCount * secondsPerQuestion

    companion object {
        fun of(raw: String?): TestMode? =
            entries.firstOrNull { it.name.equals(raw, ignoreCase = true) }
    }
}

/** "m:ss" for a countdown or a time taken. Negative values are shown as zero. */
fun formatClock(totalSeconds: Int): String {
    val safe = totalSeconds.coerceAtLeast(0)
    return "${safe / 60}:${(safe % 60).toString().padStart(2, '0')}"
}
