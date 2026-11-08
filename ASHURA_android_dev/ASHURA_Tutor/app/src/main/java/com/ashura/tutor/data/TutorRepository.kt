package com.ashura.tutor.data

import android.util.Log
import androidx.room.withTransaction
import androidx.sqlite.db.SimpleSQLiteQuery
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import com.ashura.tutor.domain.export.Json
import com.ashura.tutor.domain.assessment.QuizSource
import com.ashura.tutor.domain.library.TextChunk
import com.ashura.tutor.domain.library.TextChunker
import java.util.UUID

data class ImportResult(val itemId: String, val chunkCount: Int, val truncated: Boolean)

class TutorRepository(private val db: AppDatabase) {
    fun conversations(): Flow<List<ConversationEntity>> = db.conversations().observeAll()
    fun libraryItems(): Flow<List<LibraryItemEntity>> = db.library().observeAll()
    fun recentStudyEvents(): Flow<List<StudyEventEntity>> = db.studyEvents().observeRecent()
    fun messages(id: String): Flow<List<MessageEntity>> = db.messages().observeForConversation(id)
    fun concepts(subject: String): Flow<List<ConceptEntity>> = db.concepts().listBySubject(subject)
    fun learningStates(): Flow<List<LearningStateEntity>> = db.learningState().observeDue()
    fun unresolvedMisconceptions(): Flow<List<MisconceptionEntity>> = db.misconceptions().observeUnresolved()

    suspend fun createConversation(title: String = "New study session"): String {
        val now = System.currentTimeMillis()
        val id = UUID.randomUUID().toString()
        db.conversations().upsert(ConversationEntity(id, title, now, now))
        return id
    }

    suspend fun appendMessage(conversationId: String, role: String, content: String, source: String? = null) {
        require(role in setOf("user", "assistant", "system"))
        require(content.isNotBlank())
        val now = System.currentTimeMillis()
        db.withTransaction {
            check(db.conversations().get(conversationId) != null) { "Conversation does not exist" }
            db.messages().insert(MessageEntity(UUID.randomUUID().toString(), conversationId, role, content.trim(), now, source))
            db.conversations().touch(conversationId, now)
        }
    }

    suspend fun loadConversation(id: String): List<MessageEntity> = db.messages().listForConversation(id)

    suspend fun deleteConversation(id: String) {
        db.withTransaction {
            db.messages().deleteForConversation(id)
            db.conversations().delete(id)
        }
    }

    /** Spec §15.3: erase conversations only; notes, progress and attempts are kept. */
    suspend fun clearChatHistory() {
        db.withTransaction {
            db.messages().deleteAll()
            db.conversations().deleteAll()
        }
    }

    suspend fun saveLibraryText(title: String, body: String, mimeType: String = "text/plain", originUri: String? = null): String {
        require(title.isNotBlank() && body.isNotBlank())
        val now = System.currentTimeMillis()
        val id = UUID.randomUUID().toString()
        db.library().insert(LibraryItemEntity(id, title.trim(), body, mimeType, originUri, now, now))
        return id
    }

    /** Stores a normalised text document and its passages atomically. */
    suspend fun importText(title: String, normalizedText: String, mimeType: String): ImportResult {
        require(title.isNotBlank() && normalizedText.isNotBlank())
        val chunking = TextChunker.chunk(normalizedText)
        require(chunking.chunks.isNotEmpty()) { "Document has no readable text" }
        val now = System.currentTimeMillis()
        val itemId = UUID.randomUUID().toString()
        db.withTransaction {
            db.library().insert(LibraryItemEntity(itemId, title.trim().take(200), normalizedText, mimeType, null, now, now))
            db.chunks().insertAll(chunking.chunks.map {
                LibraryChunkEntity(UUID.randomUUID().toString(), itemId, it.ordinal, it.text, it.startOffset, it.endOffset)
            })
        }
        return ImportResult(itemId, chunking.chunks.size, chunking.truncated)
    }

    /** Passage count per item; an item with none is not searchable until re-indexed. */
    fun chunkCounts(): Flow<Map<String, Int>> =
        db.chunks().observeCounts().map { rows -> rows.associate { it.itemId to it.passages } }

    /** Rebuilds an item's passages from its stored text (spec §9.4 re-index). Returns the new passage count. */
    suspend fun reindexLibraryItem(id: String): Int {
        val body = db.library().bodyOf(id) ?: error("This note no longer exists")
        return replaceLibraryText(id, body)
    }

    /**
     * All passages grouped by note title, or one note when [itemId] is set. Built in one join so a
     * library-wide test does not run one query per note (200 study sets is a realistic library).
     */
    suspend fun testSources(itemId: String? = null): List<QuizSource> {
        val rows = if (itemId == null) db.chunks().allWithTitle() else db.chunks().withTitleForItem(itemId)
        return rows.groupBy { it.itemId }.map { (_, group) ->
            QuizSource(
                title = group.first().title,
                chunks = group.map { TextChunk(it.ordinal, it.text, it.startOffset, it.endOffset) }
            )
        }
    }

    fun testResults(): Flow<List<TestResultEntity>> = db.testResults().observeAll()

    suspend fun saveTestResult(result: TestResultEntity) = db.testResults().insert(result)

    /** The previous completed test of the same mode, used for the score-change line. */
    suspend fun previousTestResult(mode: String): TestResultEntity? = db.testResults().latestForMode(mode)

    suspend fun deleteTestResult(id: String) = db.testResults().delete(id)

    suspend fun clearTestResults() = db.testResults().deleteAll()

    suspend fun deleteLibraryItemByTitle(title: String) = db.library().deleteByTitle(title.trim())

    suspend fun deleteLibraryItem(id: String) = db.library().delete(id) // chunks and FTS rows follow via cascade/triggers

    /**
     * Replaces a note's text and re-chunks it atomically (spec §9.3: OCR output must stay editable).
     * Old chunk rows are deleted so the FTS triggers remove their index entries; new rows are then
     * inserted, keeping passage search and citations consistent with the corrected text.
     */
    suspend fun replaceLibraryText(id: String, text: String): Int {
        val normalizedText = TextChunker.normalize(text)
        require(normalizedText.isNotBlank()) { "The note would be empty" }
        val chunking = TextChunker.chunk(normalizedText)
        require(chunking.chunks.isNotEmpty()) { "The note has no readable text" }
        val now = System.currentTimeMillis()
        db.withTransaction {
            db.library().updateBody(id, normalizedText, now)
            db.chunks().deleteForItem(id)
            db.chunks().insertAll(chunking.chunks.map {
                LibraryChunkEntity(UUID.randomUUID().toString(), id, it.ordinal, it.text, it.startOffset, it.endOffset)
            })
        }
        return chunking.chunks.size
    }

    /** True when a note with the same title is already present (used to avoid duplicate study-pack imports). */
    suspend fun hasLibraryTitle(title: String): Boolean = db.library().countByTitle(title.trim()) > 0

    /** Ranked passage search with provenance (all words must match); falls back to LIKE if FTS5 is missing. */
    suspend fun searchPassages(query: String): List<ChunkHit> {
        val term = query.trim()
        val match = FtsQuery.build(term) ?: return emptyList()
        return passageQuery(match, 20, term)
    }

    /** Retrieval for a natural-language question: distinctive words OR-ed, best BM25 first, bounded. */
    suspend fun searchPassagesForQuestion(question: String, limit: Int = 8): List<ChunkHit> {
        val match = FtsQuery.forQuestion(question) ?: return emptyList()
        val longest = FtsQuery.keywords(question).maxByOrNull { it.length } ?: return emptyList()
        return passageQuery(match, limit, longest)
    }

    private suspend fun passageQuery(match: String, limit: Int, likeTerm: String): List<ChunkHit> = try {
        db.chunks().searchRaw(
            SimpleSQLiteQuery(
                "SELECT c.id AS chunkId, c.itemId AS itemId, li.title AS title, c.ordinal AS ordinal, " +
                    "c.text AS text, c.startOffset AS startOffset FROM library_chunks c " +
                    "JOIN chunks_fts ON c.rowid = chunks_fts.rowid JOIN library_items li ON li.id = c.itemId " +
                    "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
                arrayOf<Any>(match, limit)
            )
        )
    } catch (e: Exception) {
        Log.w("TutorRepository", "Passage FTS failed, using LIKE fallback", e)
        db.chunks().searchLike(likeTerm.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"), limit)
    }

    /** FTS5 ranked search (spec §10.1) with an automatic LIKE fallback if FTS5 is unavailable on this device. */
    suspend fun searchLibrary(query: String): List<LibraryItemEntity> {
        val term = query.trim()
        if (term.isEmpty()) return emptyList()
        val match = FtsQuery.build(term) ?: return emptyList()
        return try {
            db.library().searchRaw(
                SimpleSQLiteQuery(
                    "SELECT li.* FROM library_items li JOIN library_fts ON li.rowid = library_fts.rowid " +
                        "WHERE library_fts MATCH ? ORDER BY bm25(library_fts) LIMIT 30",
                    arrayOf<Any>(match)
                )
            )
        } catch (e: Exception) {
            Log.w("TutorRepository", "FTS search failed, using LIKE fallback", e)
            db.library().search(term)
        }
    }

    suspend fun recordStudyEvent(topicId: String, eventType: String, score: Double? = null) {
        require(topicId.isNotBlank() && eventType.isNotBlank())
        require(score == null || score in 0.0..1.0)
        db.studyEvents().insert(StudyEventEntity(UUID.randomUUID().toString(), topicId, eventType, score, System.currentTimeMillis()))
    }

    /** Deterministic id so saving the same concept twice does not create duplicates. */
    suspend fun saveConcept(subject: String, topic: String, level: String): String {
        require(subject.isNotBlank() && topic.isNotBlank())
        val id = "${subject.trim().lowercase()}:${topic.trim().lowercase()}"
        db.concepts().upsert(ConceptEntity(id, subject.trim(), topic.trim(), level, System.currentTimeMillis()))
        return id
    }

    suspend fun getLearningState(conceptId: String): LearningStateEntity? = db.learningState().get(conceptId)

    suspend fun upsertLearningState(
        conceptId: String,
        masteryEstimate: Double,
        confidence: Double,
        nextReviewAt: Long,
        intervalDays: Int = 1
    ) {
        db.learningState().upsert(LearningStateEntity(conceptId, masteryEstimate, confidence, nextReviewAt, intervalDays))
    }

    suspend fun attemptCount(conceptId: String): Int = db.attempts().countForConcept(conceptId)

    /**
     * Persists one attempt, its learning-state update and misconception evidence atomically (spec §19).
     * Teaching decisions (mastery, interval, which tags to resolve) are made by the caller, not here.
     */
    suspend fun commitAttempt(
        attempt: AttemptEntity,
        state: LearningStateEntity,
        recurringMisconceptionTag: String?,
        resolvedMisconceptionTags: List<String>
    ) {
        db.withTransaction {
            db.attempts().insert(attempt)
            db.learningState().upsert(state)
            if (recurringMisconceptionTag != null) {
                val id = "${attempt.conceptId}|$recurringMisconceptionTag"
                val existing = db.misconceptions().get(id)
                db.misconceptions().upsert(
                    MisconceptionEntity(
                        id = id, conceptId = attempt.conceptId, tag = recurringMisconceptionTag,
                        evidenceCount = (existing?.evidenceCount ?: 0) + 1,
                        lastSeenAt = attempt.occurredAt, resolvedAt = null
                    )
                )
            }
            if (resolvedMisconceptionTags.isNotEmpty()) {
                db.misconceptions().resolve(attempt.conceptId, resolvedMisconceptionTags, attempt.occurredAt)
            }
            db.studyEvents().insert(
                StudyEventEntity(
                    UUID.randomUUID().toString(), attempt.conceptId, "attempt_${attempt.verdict.lowercase()}",
                    if (attempt.verdict == "CORRECT") 1.0 else 0.0, attempt.occurredAt
                )
            )
        }
    }

    suspend fun chunksForItem(itemId: String): List<TextChunk> =
        db.chunks().forItem(itemId).map { TextChunk(it.ordinal, it.text, it.startOffset, it.endOffset) }

    /**
     * Complete, human-readable export of everything stored about the learner (spec §15.3 data portability).
     * Read inside one transaction so the file is a consistent snapshot. Contains private notes and answers:
     * the caller chooses where the file is saved.
     */
    suspend fun exportAllJson(): String = withContext(Dispatchers.IO) {
        db.withTransaction {
            val doc = mapOf(
                "format" to "ashura-tutor-export",
                "version" to 1,
                "exportedAt" to System.currentTimeMillis(),
                "conversations" to db.conversations().all().map { mapOf("id" to it.id, "title" to it.title, "createdAt" to it.createdAt, "updatedAt" to it.updatedAt) },
                "messages" to db.messages().all().map { mapOf("id" to it.id, "conversationId" to it.conversationId, "role" to it.role, "content" to it.content, "createdAt" to it.createdAt, "source" to it.source) },
                "libraryItems" to db.library().all().map { mapOf("id" to it.id, "title" to it.title, "text" to it.body, "mimeType" to it.mimeType, "createdAt" to it.createdAt, "updatedAt" to it.updatedAt) },
                "learningState" to db.learningState().all().map { mapOf("conceptId" to it.conceptId, "masteryEstimate" to it.masteryEstimate, "confidence" to it.confidence, "nextReviewAt" to it.nextReviewAt, "intervalDays" to it.intervalDays) },
                "attempts" to db.attempts().all().map { mapOf("id" to it.id, "conceptId" to it.conceptId, "questionId" to it.questionId, "answer" to it.answer, "verdict" to it.verdict, "hintsUsed" to it.hintsUsed, "misconceptionTag" to it.misconceptionTag, "occurredAt" to it.occurredAt) },
                "misconceptions" to db.misconceptions().all().map { mapOf("conceptId" to it.conceptId, "tag" to it.tag, "evidenceCount" to it.evidenceCount, "lastSeenAt" to it.lastSeenAt, "resolvedAt" to it.resolvedAt) },
                "testResults" to db.testResults().all().map { mapOf("id" to it.id, "mode" to it.mode, "title" to it.title, "totalQuestions" to it.totalQuestions, "correctAnswers" to it.correctAnswers, "scorePercent" to it.scorePercent, "timeTakenSeconds" to it.timeTakenSeconds, "timedOut" to it.timedOut, "startedAt" to it.startedAt, "finishedAt" to it.finishedAt) },
                "studyEvents" to db.studyEvents().all().map { mapOf("id" to it.id, "topicId" to it.topicId, "eventType" to it.eventType, "score" to it.score, "occurredAt" to it.occurredAt) }
            )
            Json.write(doc)
        }
    }

    /** Erases all learner data (spec §15.3). Triggers keep the FTS index consistent. */
    suspend fun deleteAllData() = withContext(Dispatchers.IO) { db.clearAllTables() }
}
