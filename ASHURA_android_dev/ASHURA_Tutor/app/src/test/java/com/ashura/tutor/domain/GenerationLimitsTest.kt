package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Regression guard for the “question is too long” failure: a phone-speed 1.5B model needs more
 * than 45 s and more than 384 output tokens to finish a multi-step derivation.
 */
class GenerationLimitsTest {
    @Test fun defaultsLeaveRoomForAFullDerivation() {
        val limits = GenerationLimits()
        assertTrue(limits.maxOutputTokens >= 512)
        assertTrue(limits.timeoutMillis >= 120_000)
    }
}
