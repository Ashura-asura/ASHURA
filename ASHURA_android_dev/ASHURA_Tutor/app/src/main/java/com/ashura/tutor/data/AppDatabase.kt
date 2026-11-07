package com.ashura.tutor.data

import android.content.Context
import android.util.Log
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        ConversationEntity::class,
        MessageEntity::class,
        LibraryItemEntity::class,
        StudyEventEntity::class,
        ConceptEntity::class,
        LearningStateEntity::class,
        AttemptEntity::class,
        MisconceptionEntity::class,
        LibraryChunkEntity::class
    ],
    version = 4,
    exportSchema = true
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun conversations(): ConversationDao
    abstract fun messages(): MessageDao
    abstract fun library(): LibraryDao
    abstract fun studyEvents(): StudyEventDao
    abstract fun concepts(): ConceptDao
    abstract fun learningState(): LearningStateDao
    abstract fun attempts(): AttemptDao
    abstract fun misconceptions(): MisconceptionDao
    abstract fun chunks(): ChunkDao

    companion object {
        private const val TAG = "AppDatabase"

        internal val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS concepts (" +
                        "id TEXT NOT NULL PRIMARY KEY, subject TEXT NOT NULL, " +
                        "topic TEXT NOT NULL, level TEXT NOT NULL, createdAt INTEGER NOT NULL)"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_concepts_subject ON concepts(subject)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_concepts_topic ON concepts(topic)")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS learning_state (" +
                        "conceptId TEXT NOT NULL PRIMARY KEY, masteryEstimate REAL NOT NULL, " +
                        "confidence REAL NOT NULL, nextReviewAt INTEGER NOT NULL)"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_learning_state_conceptId ON learning_state(conceptId)")
            }
        }

        /** Adds persisted spacing interval, attempts, misconceptions and the FTS5 library index. */
        internal val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE learning_state ADD COLUMN intervalDays INTEGER NOT NULL DEFAULT 1")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS attempts (" +
                        "id TEXT NOT NULL, conceptId TEXT NOT NULL, questionId TEXT NOT NULL, answer TEXT NOT NULL, " +
                        "verdict TEXT NOT NULL, hintsUsed INTEGER NOT NULL, misconceptionTag TEXT, " +
                        "occurredAt INTEGER NOT NULL, PRIMARY KEY(id))"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_attempts_conceptId ON attempts(conceptId)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_attempts_occurredAt ON attempts(occurredAt)")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS misconceptions (" +
                        "id TEXT NOT NULL, conceptId TEXT NOT NULL, tag TEXT NOT NULL, evidenceCount INTEGER NOT NULL, " +
                        "lastSeenAt INTEGER NOT NULL, resolvedAt INTEGER, PRIMARY KEY(id))"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_misconceptions_conceptId ON misconceptions(conceptId)")
                createFts(db)
            }
        }

        /** Adds passage-level storage with provenance and a chunk FTS5 index. */
        internal val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS library_chunks (" +
                        "id TEXT NOT NULL, itemId TEXT NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL, " +
                        "startOffset INTEGER NOT NULL, endOffset INTEGER NOT NULL, PRIMARY KEY(id), " +
                        "FOREIGN KEY(itemId) REFERENCES library_items(id) ON UPDATE NO ACTION ON DELETE CASCADE)"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_library_chunks_itemId ON library_chunks(itemId)")
                createChunkFts(db)
            }
        }

        internal fun createChunkFts(db: SupportSQLiteDatabase) {
            try {
                db.execSQL("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='library_chunks', content_rowid='rowid')")
                db.execSQL(
                    "CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON library_chunks BEGIN " +
                        "INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text); END"
                )
                db.execSQL(
                    "CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON library_chunks BEGIN " +
                        "INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text); END"
                )
                db.execSQL("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            } catch (e: Exception) {
                Log.w(TAG, "FTS5 unavailable for chunks; passage search will use the LIKE fallback", e)
            }
        }

        /**
         * External-content FTS5 index over library_items kept in sync by triggers. Room does not model FTS5,
         * so this lives outside the entity schema. If the device's SQLite lacks FTS5 the app keeps working:
         * the repository detects the missing table and falls back to LIKE search.
         */
        internal fun createFts(db: SupportSQLiteDatabase) {
            try {
                db.execSQL(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(" +
                        "title, body, content='library_items', content_rowid='rowid')"
                )
                db.execSQL(
                    "CREATE TRIGGER IF NOT EXISTS library_fts_ai AFTER INSERT ON library_items BEGIN " +
                        "INSERT INTO library_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body); END"
                )
                db.execSQL(
                    "CREATE TRIGGER IF NOT EXISTS library_fts_ad AFTER DELETE ON library_items BEGIN " +
                        "INSERT INTO library_fts(library_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body); END"
                )
                db.execSQL(
                    "CREATE TRIGGER IF NOT EXISTS library_fts_au AFTER UPDATE ON library_items BEGIN " +
                        "INSERT INTO library_fts(library_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body); " +
                        "INSERT INTO library_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body); END"
                )
                db.execSQL("INSERT INTO library_fts(library_fts) VALUES ('rebuild')")
            } catch (e: Exception) {
                Log.w(TAG, "FTS5 unavailable; library search will use the LIKE fallback", e)
            }
        }

        fun create(context: Context): AppDatabase =
            Room.databaseBuilder(context, AppDatabase::class.java, "ashura_tutor.db")
                .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
                .addCallback(object : RoomDatabase.Callback() {
                    override fun onCreate(db: SupportSQLiteDatabase) { createFts(db); createChunkFts(db) }
                })
                .build()
    }
}
