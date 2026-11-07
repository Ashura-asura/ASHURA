package com.ashura.tutor.data

import androidx.room.withTransaction
import kotlinx.coroutines.flow.Flow
import java.util.UUID

class TutorRepository(private val db: AppDatabase) {
    fun conversations(): Flow<List<ConversationEntity>> = db.conversations().observeAll()
    fun libraryItems(): Flow<List<LibraryItemEntity>> = db.library().observeAll()
    fun recentStudyEvents(): Flow<List<StudyEventEntity>> = db.studyEvents().observeRecent()
    fun messages(id: String): Flow<List<MessageEntity>> = db.messages().observeForConversation(id)
    fun concepts(subject: String): Flow<List<ConceptEntity>> = db.concepts().listBySubject(subject)

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

    suspend fun saveLibraryText(title: String, body: String, mimeType: String = "text/plain", originUri: String? = null): String {
        require(title.isNotBlank() && body.isNotBlank())
        val now = System.currentTimeMillis()
        val id = UUID.randomUUID().toString()
        db.library().insert(LibraryItemEntity(id, title.trim(), body, mimeType, originUri, now, now))
        return id
    }

    suspend fun searchLibrary(query: String): List<LibraryItemEntity> {
        val term = query.trim()
        return if (term.isEmpty()) emptyList() else db.library().search(term)
    }

    suspend fun recordStudyEvent(topicId: String, eventType: String, score: Double? = null) {
        require(topicId.isNotBlank() && eventType.isNotBlank())
        require(score == null || score in 0.0..1.0)
        db.studyEvents().insert(StudyEventEntity(UUID.randomUUID().toString(), topicId, eventType, score, System.currentTimeMillis()))
    }

    suspend fun saveConcept(subject: String, topic: String, level: String): String {
        require(subject.isNotBlank() && topic.isNotBlank())
        val id = UUID.randomUUID().toString()
        db.concepts().upsert(ConceptEntity(id, subject, topic, level, System.currentTimeMillis()))
        return id
    }

    suspend fun getLearningState(conceptId: String): LearningStateEntity? = db.learningState().get(conceptId)

    suspend fun upsertLearningState(
        conceptId: String,
        masteryEstimate: Double,
        confidence: Double,
        nextReviewAt: Long
    ) {
        db.learningState().upsert(LearningStateEntity(conceptId, masteryEstimate, confidence, nextReviewAt))
    }
}
