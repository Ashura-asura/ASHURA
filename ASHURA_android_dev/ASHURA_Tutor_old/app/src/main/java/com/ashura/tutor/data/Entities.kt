package com.ashura.tutor.data

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "conversations", indices = [Index("updatedAt")])
data class ConversationEntity(
    @PrimaryKey val id: String, val title: String, val createdAt: Long, val updatedAt: Long
)

@Entity(tableName = "messages", indices = [Index("conversationId"), Index("createdAt")])
data class MessageEntity(
    @PrimaryKey val id: String, val conversationId: String, val role: String,
    val content: String, val createdAt: Long, val source: String? = null
)

@Entity(tableName = "library_items", indices = [Index("title"), Index("createdAt")])
data class LibraryItemEntity(
    @PrimaryKey val id: String, val title: String, val body: String, val mimeType: String,
    val originUri: String?, val createdAt: Long, val updatedAt: Long
)

@Entity(tableName = "study_events", indices = [Index("occurredAt"), Index("topicId")])
data class StudyEventEntity(
    @PrimaryKey val id: String, val topicId: String, val eventType: String,
    val score: Double?, val occurredAt: Long
)
