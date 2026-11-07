package com.ashura.tutor.domain.library

/** What the Library shows for an imported item: size, passage count and whether search can find it (spec §9.4). */
data class ImportStatus(val sizeLabel: String, val passages: Int, val indexed: Boolean) {
    companion object {
        fun of(bodyChars: Int, passages: Int): ImportStatus {
            require(bodyChars >= 0 && passages >= 0)
            return ImportStatus(sizeLabel(bodyChars), passages, indexed = passages > 0)
        }

        /** Characters are a text-size proxy: "850 chars", "12.4k chars", "1.2M chars". */
        fun sizeLabel(chars: Int): String = when {
            chars < 1_000 -> "$chars chars"
            chars < 1_000_000 -> "${oneDecimal(chars / 1_000.0)}k chars"
            else -> "${oneDecimal(chars / 1_000_000.0)}M chars"
        }

        private fun oneDecimal(v: Double): String {
            val tenths = Math.round(v * 10)
            return "${tenths / 10}.${tenths % 10}"
        }
    }
}
