package com.ashura.tutor.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ConceptDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(concept: ConceptEntity)

    @Query("SELECT * FROM concepts WHERE id = :id LIMIT 1")
    suspend fun get(id: String): ConceptEntity?

    @Query("SELECT * FROM concepts WHERE subject = :subject ORDER BY topic")
    fun listBySubject(subject: String): Flow<List<ConceptEntity>>
}

@Dao
interface LearningStateDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(state: LearningStateEntity)

    @Query("SELECT * FROM learning_state WHERE conceptId = :conceptId LIMIT 1")
    suspend fun get(conceptId: String): LearningStateEntity?

    @Query("SELECT * FROM learning_state ORDER BY nextReviewAt ASC")
    fun observeDue(): Flow<List<LearningStateEntity>>
}
