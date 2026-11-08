package com.ashura.tutor.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.RawQuery
import androidx.sqlite.db.SupportSQLiteQuery
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

    @Query("SELECT * FROM learning_state ORDER BY conceptId")
    suspend fun all(): List<LearningStateEntity>
}

@Dao
interface AttemptDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(attempt: AttemptEntity)

    @Query("SELECT COUNT(*) FROM attempts WHERE conceptId = :conceptId")
    suspend fun countForConcept(conceptId: String): Int

    @Query("SELECT * FROM attempts ORDER BY occurredAt")
    suspend fun all(): List<AttemptEntity>
}

@Dao
interface MisconceptionDao {
    @Query("SELECT * FROM misconceptions WHERE id = :id LIMIT 1")
    suspend fun get(id: String): MisconceptionEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: MisconceptionEntity)

    @Query("SELECT * FROM misconceptions WHERE resolvedAt IS NULL ORDER BY evidenceCount DESC, lastSeenAt DESC")
    fun observeUnresolved(): Flow<List<MisconceptionEntity>>

    @Query("SELECT * FROM misconceptions ORDER BY conceptId, tag")
    suspend fun all(): List<MisconceptionEntity>

    @Query("UPDATE misconceptions SET resolvedAt = :at WHERE conceptId = :conceptId AND tag IN (:tags) AND resolvedAt IS NULL")
    suspend fun resolve(conceptId: String, tags: List<String>, at: Long)
}

@Dao
interface ChunkDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertAll(chunks: List<LibraryChunkEntity>)

    @Query("SELECT COUNT(*) FROM library_chunks WHERE itemId = :itemId")
    suspend fun countForItem(itemId: String): Int

    @Query("SELECT * FROM library_chunks WHERE itemId = :itemId ORDER BY ordinal")
    suspend fun forItem(itemId: String): List<LibraryChunkEntity>

    @Query(
        "SELECT c.itemId AS itemId, li.title AS title, c.ordinal AS ordinal, c.text AS text, " +
            "c.startOffset AS startOffset, c.endOffset AS endOffset " +
            "FROM library_chunks c JOIN library_items li ON li.id = c.itemId " +
            "ORDER BY li.createdAt, c.ordinal"
    )
    suspend fun allWithTitle(): List<ChunkWithTitle>

    @Query(
        "SELECT c.itemId AS itemId, li.title AS title, c.ordinal AS ordinal, c.text AS text, " +
            "c.startOffset AS startOffset, c.endOffset AS endOffset " +
            "FROM library_chunks c JOIN library_items li ON li.id = c.itemId " +
            "WHERE c.itemId = :itemId ORDER BY c.ordinal"
    )
    suspend fun withTitleForItem(itemId: String): List<ChunkWithTitle>

    @Query("SELECT itemId AS itemId, COUNT(*) AS passages FROM library_chunks GROUP BY itemId")
    fun observeCounts(): Flow<List<ChunkCount>>

    @Query("DELETE FROM library_chunks WHERE itemId = :itemId")
    suspend fun deleteForItem(itemId: String)

    /** FTS5 query built in the repository; user text is only a bound argument. */
    @RawQuery
    suspend fun searchRaw(query: SupportSQLiteQuery): List<ChunkHit>

    @Query(
        "SELECT c.id AS chunkId, c.itemId AS itemId, li.title AS title, c.ordinal AS ordinal, c.text AS text, c.startOffset AS startOffset " +
            "FROM library_chunks c JOIN library_items li ON li.id = c.itemId " +
            "WHERE c.text LIKE '%' || :query || '%' ESCAPE '\\' ORDER BY li.updatedAt DESC, c.ordinal LIMIT :limit"
    )
    suspend fun searchLike(query: String, limit: Int): List<ChunkHit>
}

/** Passage count per imported item, used for the Library's indexed-state line. */
data class ChunkCount(val itemId: String, val passages: Int)

/** A passage plus its note title, used to build tests across several notes in one query. */
data class ChunkWithTitle(
    val itemId: String,
    val title: String,
    val ordinal: Int,
    val text: String,
    val startOffset: Int,
    val endOffset: Int
)
