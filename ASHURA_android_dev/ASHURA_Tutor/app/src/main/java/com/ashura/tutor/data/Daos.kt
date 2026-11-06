package com.ashura.tutor.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ConversationDao {
    @Query("SELECT * FROM conversations ORDER BY updatedAt DESC")
    fun observeAll(): Flow<List<ConversationEntity>>
    @Query("SELECT * FROM conversations WHERE id = :id LIMIT 1")
    suspend fun get(id: String): ConversationEntity?
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ConversationEntity)
    @Query("UPDATE conversations SET updatedAt = :updatedAt WHERE id = :id")
    suspend fun touch(id: String, updatedAt: Long)
}

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY createdAt ASC")
    fun observeForConversation(conversationId: String): Flow<List<MessageEntity>>
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(message: MessageEntity)
}

@Dao
interface LibraryDao {
    @Query("SELECT * FROM library_items ORDER BY updatedAt DESC")
    fun observeAll(): Flow<List<LibraryItemEntity>>
    @Query("SELECT * FROM library_items WHERE title LIKE '%' || :query || '%' OR body LIKE '%' || :query || '%' ORDER BY updatedAt DESC LIMIT :limit")
    suspend fun search(query: String, limit: Int = 30): List<LibraryItemEntity>
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(item: LibraryItemEntity)
    @Query("DELETE FROM library_items WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface StudyEventDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(event: StudyEventEntity)
    @Query("SELECT * FROM study_events ORDER BY occurredAt DESC LIMIT :limit")
    fun observeRecent(limit: Int = 100): Flow<List<StudyEventEntity>>
}
