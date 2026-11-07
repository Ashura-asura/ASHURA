package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.LiteRtLmModelRuntime
import com.ashura.tutor.domain.runtime.ModelCatalog
import com.ashura.tutor.domain.runtime.RamTier
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The catalog is the only source of model downloads and imports (spec §6.3), so every entry must be
 * structurally valid, uniquely named, and pinned to an exact HTTPS artifact.
 */
class ModelCatalogTest {

    @Test fun everyEntryIsStructurallyValid() {
        for (manifest in ModelCatalog.entries) {
            assertEquals("problems in ${manifest.id}", emptyList<String>(), manifest.problems())
        }
    }

    @Test fun idsAreUniqueAndSafeAsFileNames() {
        val ids = ModelCatalog.entries.map { it.id }
        assertEquals(ids.size, ids.toSet().size)
        for (manifest in ModelCatalog.entries) {
            assertTrue(manifest.id, manifest.id.matches(Regex("^[a-z0-9][a-z0-9._-]{2,63}$")))
            assertTrue(manifest.id, LiteRtLmModelRuntime.fileName(manifest).endsWith(".litertlm"))
        }
    }

    @Test fun downloadsAreHttpsAndSizesArePinned() {
        for (manifest in ModelCatalog.entries) {
            val url = manifest.downloadUrl
            assertNotNull("${manifest.id} has no download URL", url)
            assertTrue("${manifest.id} must use HTTPS", url!!.startsWith("https://"))
            assertTrue("${manifest.id} must pin a size", manifest.sizeBytes > 0L)
            assertTrue("${manifest.id} must pin a revision", manifest.revision.length == 40)
        }
    }

    @Test fun constrainedDevicesGetTheSmallModelAndOthersGetTheCapableOne() {
        assertEquals(ModelCatalog.qwen06b.id, ModelCatalog.recommendedFor(RamTier.CONSTRAINED)?.id)
        assertEquals(ModelCatalog.qwen15b.id, ModelCatalog.recommendedFor(RamTier.STANDARD)?.id)
        assertEquals(ModelCatalog.qwen15b.id, ModelCatalog.recommendedFor(RamTier.ENHANCED)?.id)
    }

    @Test fun theCapableModelIsRefusedOnConstrainedDevices() {
        assertTrue(!ModelCatalog.qwen15b.supports(RamTier.CONSTRAINED))
        assertTrue(ModelCatalog.qwen06b.supports(RamTier.CONSTRAINED))
        assertTrue(ModelCatalog.qwen06b.supports(RamTier.ENHANCED))
    }

    @Test fun qwen3DisablesThinkingSoTheTutorGetsADirectAnswer() {
        assertTrue(ModelCatalog.qwen06b.disableThinking)
        assertTrue(!ModelCatalog.qwen15b.disableThinking)
    }

    @Test fun byIdReturnsOnlyCatalogEntries() {
        assertEquals(ModelCatalog.qwen15b, ModelCatalog.byId(ModelCatalog.qwen15b.id))
        assertEquals(null, ModelCatalog.byId("some-unvetted-model"))
    }
}
