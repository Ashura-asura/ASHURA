package com.ashura.tutor.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ConfidenceLabelTest {
    private val src = listOf("[1] Notes · passage 1")

    @Test fun calculatorResultIsVerified() =
        assertEquals(ConfidenceLabel.VERIFIED_BY_CALCULATION, ConfidenceLabel.forAnswer(ResponseMode.DETERMINISTIC, emptyList()))

    @Test fun modelWithSourcesIsSupported() =
        assertEquals(ConfidenceLabel.SUPPORTED_BY_SOURCE, ConfidenceLabel.forAnswer(ResponseMode.LOCAL_MODEL, src))

    @Test fun modelWithoutSourcesIsModelOnly() =
        assertEquals(ConfidenceLabel.MODEL_ONLY, ConfidenceLabel.forAnswer(ResponseMode.LOCAL_MODEL, emptyList()))

    @Test fun fallbackWithoutSourcesIsInsufficient() =
        assertEquals(ConfidenceLabel.INSUFFICIENT_EVIDENCE, ConfidenceLabel.forAnswer(ResponseMode.OFFLINE_FALLBACK, emptyList()))

    @Test fun fallbackWithSourcesIsSupported() =
        assertEquals(ConfidenceLabel.SUPPORTED_BY_SOURCE, ConfidenceLabel.forAnswer(ResponseMode.OFFLINE_FALLBACK, src))

    @Test fun unknownModeHasNoLabel() = assertNull(ConfidenceLabel.forAnswer(null, src))
}
