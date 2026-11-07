package com.ashura.tutor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FtsQueryTest {
    @Test fun tokensBecomeQuotedPrefixTermsAndedTogether() {
        assertEquals("\"newton\"* \"s\"* \"laws\"*", FtsQuery.build("Newton's laws"))
        assertEquals("\"photosynthesis\"*", FtsQuery.build("Photosynthesis"))
    }

    @Test fun operatorsAndQuotesCannotBeInjected() {
        assertEquals("\"a\"* \"or\"* \"b\"*", FtsQuery.build("a OR b"))
        assertEquals("\"title\"* \"x\"*", FtsQuery.build("title: \"x\" *"))
        assertEquals("\"drop\"* \"table\"*", FtsQuery.build("'); DROP TABLE--"))
    }

    @Test fun emptyOrSymbolOnlyInputIsRejected() {
        assertNull(FtsQuery.build("   "))
        assertNull(FtsQuery.build("*** --- \"\""))
    }

    @Test fun unicodeLettersAreKeptAndLengthIsBounded() {
        assertEquals("\"café\"* \"नमस्ते\"*".lowercase(), FtsQuery.build("Café नमस्ते"))
        assertEquals(12, FtsQuery.build((1..30).joinToString(" ") { "w$it" })!!.split(" ").size)
    }
}
