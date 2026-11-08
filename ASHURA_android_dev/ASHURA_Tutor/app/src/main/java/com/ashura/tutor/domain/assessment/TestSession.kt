package com.ashura.tutor.domain.assessment

/**
 * An in-progress or finished timed test. Pure data: the ViewModel supplies the clock, which keeps
 * scoring and countdown behaviour unit-testable without Android or a running timer.
 */
data class TestSession(
    val mode: TestMode,
    val title: String,
    val questions: List<ChoiceQuestion>,
    val answers: List<Int?>,
    val currentIndex: Int,
    val startedAtMillis: Long,
    val durationSeconds: Int,
    val finishedAtMillis: Long? = null,
    val timedOut: Boolean = false
) {
    init {
        require(questions.isNotEmpty()) { "A test needs at least one question" }
        require(answers.size == questions.size) { "Every question needs an answer slot" }
        require(currentIndex in questions.indices) { "currentIndex must point at a question" }
        require(durationSeconds > 0) { "A timed test needs a positive duration" }
    }

    val total: Int get() = questions.size
    val answeredCount: Int get() = answers.count { it != null }
    val unansweredCount: Int get() = total - answeredCount
    val correctCount: Int get() =
        questions.indices.count { answers[it] != null && answers[it] == questions[it].correctIndex }
    val scorePercent: Int get() = percent(correctCount, total)
    val isFinished: Boolean get() = finishedAtMillis != null
    val deadlineMillis: Long get() = startedAtMillis + durationSeconds * 1_000L

    /** Seconds left, never negative. A finished test always reports zero. */
    fun remainingSeconds(nowMillis: Long): Int {
        if (isFinished) return 0
        val millis = deadlineMillis - nowMillis
        return if (millis <= 0) 0 else ((millis + 999) / 1_000).toInt()
    }

    fun answerAt(index: Int): Int? = answers.getOrNull(index)

    /** Selecting an option only changes the current question; it never reveals correctness. */
    fun select(option: Int): TestSession {
        if (isFinished) return this
        val question = questions[currentIndex]
        if (option !in question.options.indices) return this
        return copy(answers = answers.toMutableList().also { it[currentIndex] = option })
    }

    fun goTo(index: Int): TestSession =
        if (isFinished || index !in questions.indices) this else copy(currentIndex = index)

    fun next(): TestSession = goTo(currentIndex + 1)

    fun previous(): TestSession = goTo(currentIndex - 1)

    /** Freezes the session and records whether the clock ran out. Idempotent. */
    fun finish(nowMillis: Long, timedOut: Boolean = false): TestSession {
        if (isFinished) return this
        return copy(
            finishedAtMillis = nowMillis.coerceAtLeast(startedAtMillis),
            timedOut = timedOut
        )
    }

    /** Elapsed whole seconds for a finished test; zero while it is still running. */
    val timeTakenSeconds: Int
        get() {
            val end = finishedAtMillis ?: return 0
            return ((end - startedAtMillis).coerceAtLeast(0) / 1_000).toInt()
        }

    companion object {
        fun percent(correct: Int, total: Int): Int {
            if (total <= 0) return 0
            return Math.round(correct.coerceIn(0, total) * 100.0 / total).toInt()
        }
    }
}
