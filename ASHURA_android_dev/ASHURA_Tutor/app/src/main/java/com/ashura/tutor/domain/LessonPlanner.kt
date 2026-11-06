package com.ashura.tutor.domain

/**
 * Lesson object: the inspectable structure of a topic (spec §7.1).
 * The model adapts wording; objectives and structure stay inspectable.
 */
data class Lesson(
    val subject: String,
    val topic: String,
    val level: LearnerLevel,
    val objectives: List<String>,
    val keyVocabulary: List<String> = emptyList(),
    val explanationOutline: List<String> = emptyList(),
    val workedExample: String? = null,
    val practiceQuestions: List<PracticeQuestion> = emptyList(),
    val misconceptions: List<String> = emptyList(),
    val sourceRefs: List<String> = emptyList()
)

data class PracticeQuestion(
    val id: String,
    val conceptId: String,
    val prompt: String,
    val expectedAnswer: String,
    val explanation: String? = null
)

/**
 * Lesson planner: builds a coherent topic flow with prerequisite checks
 * (spec §7.2). This is a deterministic scaffold; content packs provide the
 * actual objectives and examples.
 */
class LessonPlanner {

    fun plan(subject: String, topic: String, level: LearnerLevel): Lesson {
        return Lesson(
            subject = subject,
            topic = topic,
            level = level,
            objectives = listOf("Define $topic in your own words.", "Solve one worked example involving $topic."),
            keyVocabulary = emptyList(),
            explanationOutline = listOf(
                "What is $topic?",
                "Why does $topic matter?",
                "Worked example.",
                "Check your understanding."
            ),
            workedExample = null,
            practiceQuestions = listOf(
                PracticeQuestion(
                    id = java.util.UUID.randomUUID().toString(),
                    conceptId = topic,
                    prompt = "Explain $topic in one sentence.",
                    expectedAnswer = "A concise, correct definition of $topic.",
                    explanation = "Check against the lesson objectives."
                )
            ),
            misconceptions = emptyList(),
            sourceRefs = emptyList()
        )
    }
}
