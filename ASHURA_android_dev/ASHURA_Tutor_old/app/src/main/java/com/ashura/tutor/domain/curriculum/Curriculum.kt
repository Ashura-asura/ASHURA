package com.ashura.tutor.domain.curriculum

import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.PracticeQuestion

/** A named, correctable misunderstanding tied to a concept (spec §7.3). */
data class Misconception(val tag: String, val description: String, val correction: String)

/** One teachable concept: objectives, prerequisites, worked example, practice (spec §8.1). */
data class Topic(
    val id: String,
    val subject: String,
    val title: String,
    val level: LearnerLevel,
    val prerequisites: List<String> = emptyList(),
    val objectives: List<String>,
    val vocabulary: List<String> = emptyList(),
    val outline: List<String>,
    val workedExample: String,
    val misconceptions: List<Misconception> = emptyList(),
    val practice: List<PracticeQuestion> = emptyList(),
    val sourceRefs: List<String> = emptyList()
)

/**
 * A versioned set of topics with a validated prerequisite graph (spec §8.2).
 * Construction fails fast on duplicate ids, unknown prerequisites or cycles.
 */
class CurriculumPack(val id: String, val version: Int, val topics: List<Topic>) {

    private val byId: Map<String, Topic>

    init {
        require(topics.map { it.id }.toSet().size == topics.size) { "Duplicate topic ids in pack $id" }
        byId = topics.associateBy { it.id }
        topics.forEach { t ->
            t.prerequisites.forEach { p ->
                require(p in byId) { "Topic ${t.id} has unknown prerequisite $p" }
            }
            t.practice.forEach { q ->
                require(q.conceptId == t.id) { "Question ${q.id} conceptId must equal topic id ${t.id}" }
                q.misconceptionsByAnswer.values.forEach { tag ->
                    require(t.misconceptions.any { it.tag == tag }) { "Question ${q.id} uses undeclared misconception $tag" }
                }
            }
        }
        // Cycle detection via DFS colouring; also validates reachability order.
        val state = HashMap<String, Int>() // 1 = visiting, 2 = done
        fun visit(id: String) {
            when (state[id]) {
                2 -> return
                1 -> throw IllegalArgumentException("Prerequisite cycle involving $id")
            }
            state[id] = 1
            byId.getValue(id).prerequisites.forEach(::visit)
            state[id] = 2
        }
        topics.forEach { visit(it.id) }
    }

    fun topic(id: String): Topic? = byId[id]

    /** Finds by title (case-insensitive), optionally constrained to a subject. */
    fun find(subject: String?, title: String): Topic? = topics.firstOrNull {
        it.title.equals(title.trim(), ignoreCase = true) &&
            (subject == null || it.subject.equals(subject.trim(), ignoreCase = true))
    }

    /** Topics in an order where every prerequisite precedes the topic that needs it. */
    fun learningOrder(): List<Topic> {
        val out = LinkedHashSet<String>()
        fun add(id: String) { if (out.contains(id)) return; byId.getValue(id).prerequisites.forEach(::add); out.add(id) }
        topics.forEach { add(it.id) }
        return out.map { byId.getValue(it) }
    }

    /** Direct and indirect prerequisites below [threshold], in teaching order. */
    fun missingPrerequisites(id: String, mastery: Map<String, Double>, threshold: Double = MASTERY_THRESHOLD): List<Topic> {
        val target = byId[id] ?: return emptyList()
        val needed = LinkedHashSet<String>()
        fun collect(t: Topic) { t.prerequisites.forEach { p -> collect(byId.getValue(p)); needed.add(p) } }
        collect(target)
        return needed.map { byId.getValue(it) }.filter { (mastery[it.id] ?: 0.0) < threshold }
    }

    /** First topic in learning order that is not yet mastered and whose prerequisites all are. */
    fun nextRecommended(mastery: Map<String, Double>, threshold: Double = MASTERY_THRESHOLD): Topic? =
        learningOrder().firstOrNull { t ->
            (mastery[t.id] ?: 0.0) < threshold && t.prerequisites.all { (mastery[it] ?: 0.0) >= threshold }
        }

    companion object { const val MASTERY_THRESHOLD = 0.7 }
}
