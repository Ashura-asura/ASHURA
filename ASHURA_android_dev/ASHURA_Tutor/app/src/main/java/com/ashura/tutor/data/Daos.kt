package com.ashura.tutor.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.RawQuery
import androidx.sqlite.db.SupportSQLiteQuery
import kotlinx.coroutines.flow.Flow

@Dao
interface ConversationDao {
    @Query("SELECT * FROM conversations ORDER BY updatedAt DESC")
    fun observeAll(): Flow<List<ConversationEntity>>
    @Query("SELECT * FROM conversations ORDER BY createdAt")
    suspend fun all(): List<ConversationEntity>
    @Query("SELECT * FROM conversations WHERE id = :id LIMIT 1")
    suspend fun get(id: String): ConversationEntity?
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: ConversationEntity)
    @Query("UPDATE conversations SET updatedAt = :updatedAt WHERE id = :id")
    suspend fun touch(id: String, updatedAt: Long)
    @Query("DELETE FROM conversations")
    suspend fun deleteAll()
    @Query("DELETE FROM conversations WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY createdAt ASC")
    fun observeForConversation(conversationId: String): Flow<List<MessageEntity>>
    @Query("SELECT * FROM messages ORDER BY createdAt")
    suspend fun all(): List<MessageEntity>
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(message: MessageEntity)
    @Query("DELETE FROM messages")
    suspend fun deleteAll()
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY createdAt ASC")
    suspend fun listForConversation(conversationId: String): List<MessageEntity>
    @Query("DELETE FROM messages WHERE conversationId = :conversationId")
    suspend fun deleteForConversation(conversationId: String)
    @Query("DELETE FROM messages WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<String>)
}

@Dao
interface LibraryDao {
    @Query("SELECT * FROM library_items ORDER BY updatedAt DESC")
    fun observeAll(): Flow<List<LibraryItemEntity>>
    @Query("SELECT * FROM library_items ORDER BY createdAt")
    suspend fun all(): List<LibraryItemEntity>
    @Query("SELECT * FROM library_items WHERE title LIKE '%' || :query || '%' OR body LIKE '%' || :query || '%' ORDER BY updatedAt DESC LIMIT :limit")
    suspend fun search(query: String, limit: Int = 30): List<LibraryItemEntity>
    /** Full-text query built by [FtsQuery]; the SQL is fixed in the repository, user text is only a bound argument. */
    @RawQuery
    suspend fun searchRaw(query: SupportSQLiteQuery): List<LibraryItemEntity>
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(item: LibraryItemEntity)
    @Query("SELECT COUNT(*) FROM library_items WHERE title = :title")
    suspend fun countByTitle(title: String): Int
    @Query("UPDATE library_items SET body = :body, updatedAt = :updatedAt WHERE id = :id")
    suspend fun updateBody(id: String, body: String, updatedAt: Long)
    @Query("SELECT body FROM library_items WHERE id = :id LIMIT 1")
    suspend fun bodyOf(id: String): String?
    @Query("DELETE FROM library_items WHERE id = :id")
    suspend fun delete(id: String)
    @Query("DELETE FROM library_items WHERE title = :title")
    suspend fun deleteByTitle(title: String)
}

@Dao
interface TestResultDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(result: TestResultEntity)

    @Query("SELECT * FROM test_results ORDER BY finishedAt DESC")
    fun observeAll(): Flow<List<TestResultEntity>>

    @Query("SELECT * FROM test_results ORDER BY finishedAt")
    suspend fun all(): List<TestResultEntity>

    @Query("SELECT * FROM test_results WHERE mode = :mode ORDER BY finishedAt DESC LIMIT 1")
    suspend fun latestForMode(mode: String): TestResultEntity?

    @Query("DELETE FROM test_results WHERE id = :id")
    suspend fun delete(id: String)

    @Query("DELETE FROM test_results")
    suspend fun deleteAll()
}

@Dao
interface StudyEventDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(event: StudyEventEntity)
    @Query("SELECT * FROM study_events ORDER BY occurredAt DESC LIMIT :limit")
    fun observeRecent(limit: Int = 100): Flow<List<StudyEventEntity>>
    @Query("SELECT * FROM study_events ORDER BY occurredAt")
    suspend fun all(): List<StudyEventEntity>
}
