package com.ashura.tutor.domain

import com.ashura.tutor.domain.curriculum.CurriculumPack
import com.ashura.tutor.domain.curriculum.SeedCurriculum

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
    val sourceRefs: List<String> = emptyList(),
    /** Stable concept id when the lesson comes from a curriculum pack; null for the generic scaffold. */
    val topicId: String? = null,
    /** True when no curriculum content exists for the topic; the lesson is only a study scaffold. */
    val isGenericScaffold: Boolean = false
)

/**
 * A practice item. Questions with [selfAssessed] = false have a machine-checkable answer
 * (see AnswerChecker); selfAssessed questions rely on the learner's own judgement.
 */
data class PracticeQuestion(
    val id: String,
    val conceptId: String,
    val prompt: String,
    val expectedAnswer: String,
    val explanation: String? = null,
    /** Extra accepted answers (e.g. "0.5" for "1/2"). The [expectedAnswer] is always accepted. */
    val acceptedAnswers: List<String> = emptyList(),
    /** Progressive hints, weakest first. */
    val hints: List<String> = emptyList(),
    /** Known wrong answer -> misconception tag (see Misconception in the topic). */
    val misconceptionsByAnswer: Map<String, String> = emptyMap(),
    /** Absolute tolerance for numeric comparison; 0 means exact rational equality. */
    val tolerance: Double = 0.0,
    /** For "simplify" questions: a correct value in non-lowest terms is not accepted. */
    val requireLowestTerms: Boolean = false,
    val selfAssessed: Boolean = false
)

/**
 * Lesson planner: builds a lesson from a curriculum pack (spec §7.2, §8).
 * Unknown topics get an explicitly-labelled generic scaffold instead of invented content.
 */
class LessonPlanner(private val pack: CurriculumPack = SeedCurriculum.pack) {

    fun plan(subject: String, topic: String, level: LearnerLevel): Lesson {
        val found = pack.find(subject, topic)
        if (found != null) {
            return Lesson(
                subject = found.subject,
                topic = found.title,
                level = found.level,
                objectives = found.objectives,
                keyVocabulary = found.vocabulary,
                explanationOutline = found.outline,
                workedExample = found.workedExample,
                practiceQuestions = found.practice,
                misconceptions = found.misconceptions.map { it.description },
                sourceRefs = found.sourceRefs,
                topicId = found.id
            )
        }
        return Lesson(
            subject = subject,
            topic = topic,
            level = level,
            objectives = listOf("Define $topic in your own words.", "Solve one worked example involving $topic."),
            explanationOutline = listOf(
                "What is $topic?", "Why does $topic matter?", "Worked example.", "Check your understanding."
            ),
            practiceQuestions = listOf(
                PracticeQuestion(
                    id = "generic:$topic",
                    conceptId = topic,
                    prompt = "Explain $topic in one sentence.",
                    expectedAnswer = "A concise, correct definition of $topic.",
                    explanation = "Check against the lesson objectives.",
                    selfAssessed = true
                )
            ),
            isGenericScaffold = true
        )
    }
}
