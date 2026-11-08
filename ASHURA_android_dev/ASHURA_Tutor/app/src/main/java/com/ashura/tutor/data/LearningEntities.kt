package com.ashura.tutor.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "concepts",
    indices = [Index("subject"), Index("topic")]
)
data class ConceptEntity(
    @PrimaryKey val id: String,
    val subject: String,
    val topic: String,
    val level: String,
    val createdAt: Long = System.currentTimeMillis()
)

@Entity(
    tableName = "learning_state",
    indices = [Index("conceptId")]
)
data class LearningStateEntity(
    @PrimaryKey val conceptId: String,
    val masteryEstimate: Double = 0.0,
    val confidence: Double = 0.0,
    val nextReviewAt: Long = 0,
    /** Current spaced-repetition interval; persisted so mastery accumulates across sessions. */
    @ColumnInfo(defaultValue = "1") val intervalDays: Int = 1
)

/** One answered practice question (spec §19 Attempt). Stays on-device; deletable via delete-all-data. */
@Entity(tableName = "attempts", indices = [Index("conceptId"), Index("occurredAt")])
data class AttemptEntity(
    @PrimaryKey val id: String,
    val conceptId: String,
    val questionId: String,
    val answer: String,
    /** CORRECT / INCORRECT, or SELF_* for self-assessed items. */
    val verdict: String,
    val hintsUsed: Int,
    val misconceptionTag: String?,
    val occurredAt: Long
)

/** Evidence-backed misconception record (spec §7.3). id = "conceptId|tag". */
@Entity(tableName = "misconceptions", indices = [Index("conceptId")])
data class MisconceptionEntity(
    @PrimaryKey val id: String,
    val conceptId: String,
    val tag: String,
    val evidenceCount: Int,
    val lastSeenAt: Long,
    val resolvedAt: Long?
)

/** A retrievable passage of an imported document; deleted with its parent item (spec §10.1 provenance). */
@Entity(
    tableName = "library_chunks",
    foreignKeys = [ForeignKey(entity = LibraryItemEntity::class, parentColumns = ["id"], childColumns = ["itemId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("itemId")]
)
data class LibraryChunkEntity(
    @PrimaryKey val id: String,
    val itemId: String,
    val ordinal: Int,
    val text: String,
    val startOffset: Int,
    val endOffset: Int
)

/**
 * One finished timed test (spec §3.4 / §19 assessment result). The per-question choices are not
 * stored, only the aggregate marks, time and mode, which is what the history and score-change view
 * need. Deleted with the rest of the learner data by delete-all-data.
 */
@Entity(tableName = "test_results", indices = [Index("finishedAt"), Index("mode")])
data class TestResultEntity(
    @PrimaryKey val id: String,
    val mode: String,
    val title: String,
    val totalQuestions: Int,
    val correctAnswers: Int,
    val scorePercent: Int,
    val timeTakenSeconds: Int,
    val timedOut: Boolean,
    val startedAt: Long,
    val finishedAt: Long
)

/** Search result row: a passage plus where it came from. Not a table. */
data class ChunkHit(
    val chunkId: String,
    val itemId: String,
    val title: String,
    val ordinal: Int,
    val text: String,
    val startOffset: Int
)
