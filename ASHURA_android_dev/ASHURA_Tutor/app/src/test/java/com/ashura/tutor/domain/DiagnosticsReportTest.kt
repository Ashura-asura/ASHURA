package com.ashura.tutor.domain

import com.ashura.tutor.domain.export.DiagnosticsReport
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DiagnosticsReportTest {

    private fun report(backend: String? = "CPU") = DiagnosticsReport(
        generatedAt = 1_700_000_000_000,
        appVersion = "0.5.7",
        androidVersion = "14",
        deviceModel = "Pixel \"4a\"",
        deviceManufacturer = "Google",
        supportedAbis = "arm64-v8a,armeabi-v7a",
        ramTier = "LOW",
        lowRamDevice = true,
        totalRamMb = 3_600,
        freeStorageBytes = 4_500_000_000,
        backend = backend,
        loadMillis = 2_100,
        firstTokenMillis = 3_400,
        generationMillis = 12_000,
        estimatedTokens = 64,
        tokensPerSecond = 5.3,
        heapUsedMb = 512
    )

    @Test fun writesValidJsonWithMeasuredCounters() {
        val json = report().toJson()
        val obj = JSONObject(json)
        assertEquals("Pixel \"4a\"", obj.getString("deviceModel"))
        assertEquals("arm64-v8a,armeabi-v7a", obj.getString("supportedAbis"))
        assertEquals(2_100, obj.getLong("loadMillis"))
        assertEquals(5.3, obj.getDouble("tokensPerSecond"), 0.0001)
        assertEquals(512, obj.getLong("heapUsedMb"))
        assertTrue(obj.getBoolean("lowRamDevice"))
        assertTrue(obj.getString("privacy").contains("No questions"))
    }

    @Test fun omitsRuntimeKeysWhenNoModelHasRun() {
        val obj = JSONObject(report(backend = null).toJson())
        assertFalse(obj.has("backend"))
        assertFalse(obj.has("tokensPerSecond"))
        assertEquals("Google", obj.getString("deviceManufacturer"))
    }

    @Test fun containsOnlyCountersAndDeviceMetadata() {
        val obj = JSONObject(report().toJson())
        val allowed = setOf(
            "generatedAt", "appVersion", "androidVersion", "deviceModel", "deviceManufacturer",
            "supportedAbis", "ramTier", "lowRamDevice", "totalRamMb", "freeStorageBytes",
            "backend", "loadMillis", "firstTokenMillis", "generationMillis", "estimatedTokens",
            "tokensPerSecond", "heapUsedMb", "privacy"
        )
        val keys = HashSet<String>()
        val iterator = obj.keys()
        while (iterator.hasNext()) keys.add(iterator.next())
        assertEquals(allowed, keys)
    }
}
