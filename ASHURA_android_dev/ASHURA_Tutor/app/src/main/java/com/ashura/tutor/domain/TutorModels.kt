package com.ashura.tutor.domain

data class TutorRequest(
    val question: String,
    val learnerLevel: LearnerLevel = LearnerLevel.UNKNOWN,
    val language: String = "en",
    val retrievedContext: List<ContextSnippet> = emptyList()
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
