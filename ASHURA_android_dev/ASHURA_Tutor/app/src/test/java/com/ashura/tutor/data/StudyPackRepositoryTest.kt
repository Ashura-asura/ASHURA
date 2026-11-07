package com.ashura.tutor.data

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class StudyPackRepositoryTest {

    private lateinit var packs: StudyPackRepository

    @Before fun setUp() {
        packs = StudyPackRepository(ApplicationProvider.getApplicationContext<Application>().assets)
    }

    @Test fun catalogHasTwentyVerifiedSetsPerSubject() {
        val library = packs.loadCatalog()
        assertEquals(1, library.version)
        assertEquals("CC BY-SA 4.0", library.license)
        assertEquals(10, library.subjects.size)
        assertEquals(200, library.count)

        library.subjects.forEach { subject ->
            assertEquals("${subject.id} should have 20 sets", 20, subject.sets.size)
            val titles = subject.sets.map { it.title }
            assertEquals("duplicate titles in ${subject.id}", titles.distinct().size, titles.size)
            subject.sets.forEach { set ->
                assertEquals(subject.id, set.subjectId)
                assertEquals(subject.name, set.subjectName)
                assertTrue(set.file.startsWith("${subject.id}/"))
                assertTrue(set.source.startsWith("https://en.wikipedia.org/wiki/"))
                assertTrue(set.chars > 400)
                assertEquals(64, set.sha256.length)
            }
        }
    }

    @Test fun everyAssetMatchesItsRecordedChecksum() = runBlocking {
        val library = packs.loadCatalog()
        var checked = 0
        library.subjects.forEach { subject ->
            subject.sets.forEach { set ->
                val text = packs.readSet(set)
                assertTrue("empty note: ${set.file}", text.isNotBlank())
                assertTrue("missing heading: ${set.file}", text.startsWith("# "))
                assertFalse("front matter leaked: ${set.file}", text.startsWith("---"))
                checked++
            }
        }
        assertEquals(library.count, checked)
    }

    @Test fun tamperedChecksumIsRejected() = runBlocking {
        val library = packs.loadCatalog()
        val set = library.allSets.first()
        val tampered = set.copy(sha256 = "0".repeat(64))
        try {
            packs.readSet(tampered)
            throw AssertionError("expected a checksum failure")
        } catch (expected: IllegalArgumentException) {
            assertTrue(expected.message!!.contains("integrity"))
        }
    }
}
