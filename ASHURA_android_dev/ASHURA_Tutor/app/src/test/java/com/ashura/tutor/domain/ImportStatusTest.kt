package com.ashura.tutor.domain

import com.ashura.tutor.domain.library.ImportStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ImportStatusTest {
    @Test fun smallTextIsShownInChars() = assertEquals("850 chars", ImportStatus.sizeLabel(850))
    @Test fun thousandsUseK() = assertEquals("12.4k chars", ImportStatus.sizeLabel(12_400))
    @Test fun millionsUseM() = assertEquals("1.2M chars", ImportStatus.sizeLabel(1_200_000))
    @Test fun roundsToOneDecimal() = assertEquals("1.0k chars", ImportStatus.sizeLabel(1_000))
    @Test fun withPassagesIsIndexed() {
        val s = ImportStatus.of(5_000, 4)
        assertTrue(s.indexed); assertEquals(4, s.passages)
    }
    @Test fun withoutPassagesIsNotIndexed() = assertFalse(ImportStatus.of(5_000, 0).indexed)
}
