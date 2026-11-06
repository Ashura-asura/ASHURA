package com.ashura.tutor.data

import androidx.room.Entity
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
    val nextReviewAt: Long = 0
)
