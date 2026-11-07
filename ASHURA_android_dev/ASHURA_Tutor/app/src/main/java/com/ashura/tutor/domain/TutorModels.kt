package com.ashura.tutor.domain

/**
 * How the tutor should respond (spec §1.2 B/C). DIRECT explains and checks; SOCRATIC asks a guiding
 * question first and withholds the final answer so the learner has to reason.
 */
enum class TutorStyle { DIRECT, SOCRATIC }

data class TutorRequest(
    val question: String,
    val learnerLevel: LearnerLevel = LearnerLevel.UNKNOWN,
    val language: String = "en",
    val style: TutorStyle = TutorStyle.DIRECT,
    val retrievedContext: List<ContextSnippet> = emptyList(),
    /** True when the learner's imported notes were searched for this request (so "nothing found" is meaningful). */
    val notesSearched: Boolean = false
)
enum class LearnerLevel { SCHOOL, BACHELOR, MASTER, UNKNOWN }
data class ContextSnippet(val title: String, val text: String, val sourceLabel: String)
data class TutorResponse(
    val answer: String,
    val mode: ResponseMode,
    val citations: List<String> = emptyList(),
    val limitation: String? = null
)
enum class ResponseMode { DETERMINISTIC, LOCAL_MODEL, OFFLINE_FALLBACK }
