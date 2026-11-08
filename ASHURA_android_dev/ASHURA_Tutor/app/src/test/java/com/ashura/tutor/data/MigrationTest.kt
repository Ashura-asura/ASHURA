package com.ashura.tutor.data

import android.content.Context
import androidx.room.Room
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Verifies the additive Room migration chain against a real SQLite engine (Robolectric).
 * Room validates the migrated schema against the entities on open, so a missing column,
 * index or wrong nullability fails the test rather than reaching a device.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MigrationTest {

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val dbName = "migration-test.db"

    @After
    fun cleanUp() {
        context.deleteDatabase(dbName)
    }

    @Test
    fun migrate1To5PreservesData() = assertMigration(1)

    @Test
    fun migrate2To5PreservesData() = assertMigration(2)

    @Test
    fun migrate3To5PreservesData() = assertMigration(3)

    @Test
    fun migrate4To5PreservesData() = assertMigration(4)

    private fun assertMigration(fromVersion: Int) {
        createLegacyDatabase(fromVersion)

        val database = Room.databaseBuilder(context, AppDatabase::class.java, dbName)
            .addMigrations(
                AppDatabase.MIGRATION_1_2,
                AppDatabase.MIGRATION_2_3,
                AppDatabase.MIGRATION_3_4,
                AppDatabase.MIGRATION_4_5
            )
            .allowMainThreadQueries()
            .build()

        try {
            val support = database.openHelper.writableDatabase
            assertEquals(5, support.version)
            assertEquals(
                "library_chunks",
                support.query("SELECT name FROM sqlite_master WHERE type='table' AND name='library_chunks'")
                    .use { it.moveToFirst(); it.getString(0) }
            )
            assertEquals(
                "test_results",
                support.query("SELECT name FROM sqlite_master WHERE type='table' AND name='test_results'")
                    .use { it.moveToFirst(); it.getString(0) }
            )

            runBlocking {
                assertEquals("Legacy conversation", database.conversations().get("c1")?.title)
                assertEquals("Legacy note body", database.library().bodyOf("l1"))
                assertEquals(0, database.testResults().all().size)
                if (fromVersion >= 2) {
                    val state = database.learningState().get("t1")
                    assertEquals(0.5, state?.masteryEstimate ?: -1.0, 0.0001)
                    assertEquals(1, state?.intervalDays)
                } else {
                    assertNull(database.learningState().get("t1"))
                }
            }
        } finally {
            database.close()
        }
    }

    /**
     * Builds the version-[version] database by creating the version-1 schema and replaying the
     * real migration objects up to [version]. This keeps the fixtures tied to the production SQL.
     */
    private fun createLegacyDatabase(version: Int) {
        val configuration = SupportSQLiteOpenHelper.Configuration.builder(context)
            .name(dbName)
            .callback(object : SupportSQLiteOpenHelper.Callback(1) {
                override fun onCreate(db: SupportSQLiteDatabase) = createVersionOne(db)
                override fun onUpgrade(db: SupportSQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit
            })
            .build()

        val helper = FrameworkSQLiteOpenHelperFactory().create(configuration)
        try {
            val db = helper.writableDatabase
            db.execSQL(
                "INSERT INTO conversations (id, title, createdAt, updatedAt) " +
                    "VALUES ('c1', 'Legacy conversation', 1, 2)"
            )
            db.execSQL(
                "INSERT INTO library_items (id, title, body, mimeType, originUri, createdAt, updatedAt) " +
                    "VALUES ('l1', 'Legacy note', 'Legacy note body', 'text/plain', NULL, 1, 2)"
            )
            if (version >= 2) {
                AppDatabase.MIGRATION_1_2.migrate(db)
                db.version = 2
                db.execSQL(
                    "INSERT INTO learning_state (conceptId, masteryEstimate, confidence, nextReviewAt) " +
                        "VALUES ('t1', 0.5, 0.4, 100)"
                )
            }
            if (version >= 3) {
                AppDatabase.MIGRATION_2_3.migrate(db)
                db.version = 3
            }
            if (version >= 4) {
                AppDatabase.MIGRATION_3_4.migrate(db)
                db.version = 4
            }
        } finally {
            helper.close()
        }
    }

    /** Exactly the version-1 tables (the ones untouched by later additive migrations). */
    private fun createVersionOne(db: SupportSQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `conversations` (`id` TEXT NOT NULL, `title` TEXT NOT NULL, " +
                "`createdAt` INTEGER NOT NULL, `updatedAt` INTEGER NOT NULL, PRIMARY KEY(`id`))"
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_conversations_updatedAt` ON `conversations` (`updatedAt`)")

        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `messages` (`id` TEXT NOT NULL, `conversationId` TEXT NOT NULL, " +
                "`role` TEXT NOT NULL, `content` TEXT NOT NULL, `createdAt` INTEGER NOT NULL, `source` TEXT, " +
                "PRIMARY KEY(`id`))"
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_messages_conversationId` ON `messages` (`conversationId`)")
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_messages_createdAt` ON `messages` (`createdAt`)")

        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `library_items` (`id` TEXT NOT NULL, `title` TEXT NOT NULL, " +
                "`body` TEXT NOT NULL, `mimeType` TEXT NOT NULL, `originUri` TEXT, `createdAt` INTEGER NOT NULL, " +
                "`updatedAt` INTEGER NOT NULL, PRIMARY KEY(`id`))"
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_library_items_title` ON `library_items` (`title`)")
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_library_items_createdAt` ON `library_items` (`createdAt`)")

        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `study_events` (`id` TEXT NOT NULL, `topicId` TEXT NOT NULL, " +
                "`eventType` TEXT NOT NULL, `score` REAL, `occurredAt` INTEGER NOT NULL, PRIMARY KEY(`id`))"
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_study_events_occurredAt` ON `study_events` (`occurredAt`)")
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_study_events_topicId` ON `study_events` (`topicId`)")
    }
}
