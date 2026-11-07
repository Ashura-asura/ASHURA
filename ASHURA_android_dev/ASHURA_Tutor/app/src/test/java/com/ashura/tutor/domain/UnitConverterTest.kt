package com.ashura.tutor.domain

import com.ashura.tutor.domain.math.UnitConverter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UnitConverterTest {
    private fun conv(s: String): String {
        val req = UnitConverter.parse(s) ?: return "NOPARSE"
        return when (val r = UnitConverter.convert(req)) {
            is UnitConverter.Result.Ok -> r.text
            is UnitConverter.Result.Error -> "ERR:" + r.message
        }
    }

    @Test fun length() {
        assertEquals("5 km = 5000 m", conv("convert 5 km to m"))
        assertEquals("1 mile = 1.609344 km", conv("1 mile in km"))
        assertEquals("12 inches = 0.3048 m", conv("12 inches to m"))
    }

    @Test fun massTimeVolumeSpeed() {
        assertEquals("2 kg = 2000 g", conv("2 kg to g"))
        assertEquals("2 hours = 120 min", conv("2 hours to min"))
        assertEquals("1500 ml = 1.5 l", conv("1500 ml to l"))
        assertEquals("36 km/h = 10 m/s", conv("36 km/h to m/s"))
    }

    @Test fun temperature() {
        assertEquals("100 c = 212 f", conv("100 c to f"))
        assertEquals("32 f = 0 c", conv("32 f to c"))
        assertEquals("0 c = 273.15 k", conv("0 c to k"))
    }

    @Test fun dimensionMismatchIsRejected() {
        assertTrue(conv("5 kg to m").startsWith("ERR:"))
    }

    @Test fun unknownUnitsAndTextAreNotHandled() {
        assertNull(UnitConverter.parse("5 foo to bar"))
        assertNull(UnitConverter.parse("explain 5 in detail"))
        assertNotNull(UnitConverter.parse("5 km to m"))
    }
}
