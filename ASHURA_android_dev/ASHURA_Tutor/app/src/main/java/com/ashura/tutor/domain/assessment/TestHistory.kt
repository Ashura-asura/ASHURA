package com.ashura.tutor.domain.assessment

/** A finished test reduced to the numbers the history and result screens need. */
data class TestResultSummary(
    val id: String,
    val mode: String,
    val title: String,
    val correct: Int,
    val total: Int,
    val timeTakenSeconds: Int,
    val timedOut: Boolean,
    val finishedAt: Long
) {
    val percent: Int get() = TestSession.percent(correct, total)
}

/** One history row plus its change from the previous test in the same mode. */
data class TestResultChange(
    val result: TestResultSummary,
    val previous: TestResultSummary?,
    val marksDelta: Int?,
    val percentDelta: Int?
)

/**
 * Builds the score-change history without hiding mixed test lengths: a result is compared with the
 * previous result of the same mode, because +5 marks on a 20-question test is not the same gain as
 * +5 on a 50-question test.
 */
object TestHistory {
    fun withChanges(resultsNewestFirst: List<TestResultSummary>): List<TestResultChange> {
        val lastByMode = HashMap<String, TestResultSummary>()
        val oldestFirst = ArrayList<TestResultChange>(resultsNewestFirst.size)
        // Walk from the oldest result forward so "previous" really is the earlier test.
        for (result in resultsNewestFirst.asReversed()) {
            val previous = lastByMode[result.mode]
            oldestFirst += TestResultChange(
                result = result,
                previous = previous,
                marksDelta = previous?.let { result.correct - it.correct },
                percentDelta = previous?.let { result.percent - it.percent }
            )
            lastByMode[result.mode] = result
        }
        return oldestFirst.asReversed()
    }
}
