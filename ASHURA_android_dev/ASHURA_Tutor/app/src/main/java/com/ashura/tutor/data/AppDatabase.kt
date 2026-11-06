package com.ashura.tutor.data

import android.content.Context
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
        LearningStateEntity::class
    ],
    version = 2,
    exportSchema = true
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun conversations(): ConversationDao
    abstract fun messages(): MessageDao
    abstract fun library(): LibraryDao
    abstract fun studyEvents(): StudyEventDao
    abstract fun concepts(): ConceptDao
    abstract fun learningState(): LearningStateDao

    companion object {
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    "CREATE TABLE IF NOT EXISTS concepts (" +
                        "id TEXT NOT NULL PRIMARY KEY, subject TEXT NOT NULL, " +
                        "topic TEXT NOT NULL, level TEXT NOT NULL, createdAt INTEGER NOT NULL)"
                )
                database.execSQL("CREATE INDEX IF NOT EXISTS index_concepts_subject ON concepts(subject)")
                database.execSQL("CREATE INDEX IF NOT EXISTS index_concepts_topic ON concepts(topic)")
                database.execSQL(
                    "CREATE TABLE IF NOT EXISTS learning_state (" +
                        "conceptId TEXT NOT NULL PRIMARY KEY, masteryEstimate REAL NOT NULL, " +
                        "confidence REAL NOT NULL, nextReviewAt INTEGER NOT NULL)"
                )
                database.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_learning_state_conceptId " +
                        "ON learning_state(conceptId)"
                )
            }
        }

        fun create(context: Context): AppDatabase =
            Room.databaseBuilder(context, AppDatabase::class.java, "ashura_tutor.db")
                .addMigrations(MIGRATION_1_2)
                .build()
    }
}
