package com.ashura.tutor.data

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Confirms that the new clear/delete actions remove only what they promise. The database is
 * in-memory, so this is a JVM (Robolectric) test and does not touch phone storage.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DataControlsTest {

    private lateinit var db: AppDatabase
    private lateinit var repository: TutorRepository

    @Before
    fun setUp() {
        val context: Context = ApplicationProvider.getApplicationContext()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = TutorRepository(db)
    }

    @After
    fun tearDown() {
        db.close()
    }

    private fun result(id: String) = TestResultEntity(
        id = id,
        mode = "QUICK",
        title = "All your notes",
        totalQuestions = 20,
        correctAnswers = 12,
        scorePercent = 60,
        timeTakenSeconds = 300,
        timedOut = false,
        startedAt = 1_000,
        finishedAt = 301_000
    )

    @Test
    fun clearingTestHistoryKeepsLibraryNotes() = runBlocking {
        repository.importText(
            "Legacy physics",
            "Gravity is a force that pulls two masses toward each other. " +
                "Friction is a force that opposes motion between two touching surfaces.",
            "text/plain"
        )
        repository.saveTestResult(result("r1"))
        repository.saveTestResult(result("r2"))

        repository.clearTestResults()

        assertEquals(0, db.testResults().all().size)
        assertEquals(1, db.library().all().size)
        assertEquals("Legacy physics", db.library().all().first().title)
    }

    @Test
    fun removingOneStudySetKeepsOtherNotesAndTestResults() = runBlocking {
        repository.importText(
            "Physics",
            "Gravity is a force that pulls two masses toward each other.",
            "text/plain"
        )
        repository.importText(
            "Chemistry",
            "An atom is the smallest unit of an element that keeps its chemical properties.",
            "text/plain"
        )
        repository.saveTestResult(result("r1"))

        repository.deleteLibraryItemByTitle("Physics")

        assertEquals(listOf("Chemistry"), db.library().all().map { it.title })
        assertEquals(1, db.testResults().all().size)
    }
}
