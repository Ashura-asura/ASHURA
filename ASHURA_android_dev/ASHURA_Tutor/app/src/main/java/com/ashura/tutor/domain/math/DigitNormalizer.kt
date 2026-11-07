package com.ashura.tutor.domain.math

/** Maps any Unicode decimal digit (e.g. Devanagari १२३, Arabic-Indic ٣) to ASCII 0-9 so Nepali/Hindi/Arabic learners can type answers naturally. */
object DigitNormalizer {
    fun toAscii(s: String): String {
        if (s.all { it.code < 128 }) return s
        val sb = StringBuilder(s.length)
        for (c in s) {
            if (c.code >= 128 && Character.isDigit(c)) sb.append('0' + Character.digit(c, 10)) else sb.append(c)
        }
        return sb.toString()
    }
}
