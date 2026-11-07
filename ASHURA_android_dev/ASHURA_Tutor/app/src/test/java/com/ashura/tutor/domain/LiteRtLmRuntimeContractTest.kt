package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.LiteRtLmModelRuntime
import com.ashura.tutor.domain.runtime.LoadResult
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.RamTier
import com.ashura.tutor.domain.runtime.ResourceBudget
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Host-side contract checks for the LiteRT-LM adapter. They never initialise the native engine: the
 * refusal paths run before any LiteRT-LM call, so they are safe on a JVM without the AAR's `.so`
 * libraries. Real loading, generation and cancellation need a device (docs/RUNTIME_INTEGRATION.md).
 */
class LiteRtLmRuntimeContractTest {

    private fun runtime(): LiteRtLmModelRuntime {
        val root = Files.createTempDirectory("ashura-litertlm").toFile().apply { deleteOnExit() }
        return LiteRtLmModelRuntime(modelsDir = File(root, "models"), cacheDir = File(root, "cache"))
    }

    private fun manifest(id: String = "qwen-test-model") = ModelManifest(
        id = id,
        revision = "a".repeat(40),
        artifactSha256 = "b".repeat(64),
        chatTemplate = "qwen2.5-chatml",
        quantization = "test",
        contextTokens = 2048,
        license = "Apache-2.0",
        minimumTier = RamTier.CONSTRAINED,
        sizeBytes = 128
    )

    @Test fun unloadingTwiceIsSafeAndHealthStaysConsistent() {
        val runtime = runtime()
        runtime.unload()
        runtime.unload()
        assertEquals(runtime.isAvailable, runtime.health().loaded)
        assertTrue(!runtime.health().loaded)
    }

    @Test fun anInvalidManifestIsRefusedBeforeTheNativeEngineIsTouched() = runBlocking {
        val runtime = runtime()
        val bad = ModelManifest("m", "", "zz", "zz", "chatml", "Q4", 2048, "MIT", RamTier.CONSTRAINED)
        val result = runtime.load(bad, ResourceBudget(1024, 256, 30_000))
        assertTrue(result is LoadResult.Failed)
        assertTrue((result as LoadResult.Failed).reason.contains("Manifest invalid"))
        assertTrue(!runtime.health().loaded)
    }

    @Test fun aMissingModelFileIsReportedHonestly() = runBlocking {
        val runtime = runtime()
        val result = runtime.load(manifest(), ResourceBudget(1024, 256, 30_000))
        assertTrue(result is LoadResult.Failed)
        assertTrue((result as LoadResult.Failed).reason.contains("missing"))
        assertTrue(!runtime.health().loaded)
    }

    @Test fun generatingWithoutALoadedModelFailsLoudly() {
        val runtime = runtime()
        val error = assertThrows(IllegalStateException::class.java) {
            runBlocking { runtime.generate(TutorRequest("hi"), GenerationLimits()) }
        }
        assertTrue(error.message!!.contains("No local model is loaded"))
    }

    @Test fun fileNamesRejectUnsafeIds() {
        assertThrows(IllegalArgumentException::class.java) { LiteRtLmModelRuntime.fileName(manifest("../escape")) }
        assertEquals("qwen-test-model.litertlm", LiteRtLmModelRuntime.fileName(manifest()))
    }
}
