package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.LoadResult
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.RamTier
import com.ashura.tutor.domain.runtime.ResourceBudget
import com.ashura.tutor.domain.runtime.UnavailableModelRuntime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine

/**
 * Behaviour every [ModelRuntime] must satisfy (spec §6.2). A real runtime (MediaPipe / llama.cpp) adds a subclass that
 * returns its instance from [newRuntime]; the same tests then gate it. Cancellation-under-load and memory checks need a
 * device and live in the benchmark harness described in docs/RUNTIME_INTEGRATION.md.
 */
abstract class ModelRuntimeContract {
    abstract fun newRuntime(): ModelRuntime

    private fun <T> run(block: suspend () -> T): Result<T> {
        var out: Result<T>? = null
        block.startCoroutine(Continuation(EmptyCoroutineContext) { out = it })
        return out ?: Result.failure(IllegalStateException("did not complete synchronously"))
    }

    @Test fun unloadIsIdempotentAndHealthIsConsistent() {
        val r = newRuntime()
        r.unload(); r.unload()
        assertEquals(r.isAvailable, r.health().loaded)
    }

    @Test fun invalidManifestIsRefusedBeforeAnythingIsLoaded() {
        val r = newRuntime()
        val bad = ModelManifest("m", "", "zz", "zz", "chatml", "Q4", 2048, "MIT", RamTier.CONSTRAINED)
        val result = run { r.load(bad, ResourceBudget(1024, 256, 30_000)) }.getOrThrow()
        assertTrue(result is LoadResult.Failed)
        r.health() // a failed load must leave the runtime queryable, not crashed
    }

    @Test fun generatingWithoutAModelFailsLoudlyNotSilently() {
        val r = newRuntime()
        if (!r.isAvailable) {
            val res = run { r.generate(TutorRequest("hi"), GenerationLimits()) }
            assertTrue(res.isFailure)
        }
    }
}

class UnavailableRuntimeContractTest : ModelRuntimeContract() {
    override fun newRuntime(): ModelRuntime = UnavailableModelRuntime()
}
