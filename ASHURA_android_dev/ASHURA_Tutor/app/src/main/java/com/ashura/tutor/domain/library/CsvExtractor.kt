package com.ashura.tutor.domain.library

/**
 * Minimal, dependency-free CSV/TSV extractor (spec §9.1, §9.6).
 *
 * A spreadsheet or CSV must not be flattened into an unlabelled paragraph: this keeps the sheet
 * name and each cell's row/column reference (A1, B2, …) so citations can point at the exact cell and
 * the quiz builder can ask about a specific row. Quoted fields, escaped quotes and newlines inside
 * quotes are handled; every loop is bounded.
 */
object CsvExtractor {
    const val MAX_ROWS = 20_000
    const val MAX_COLUMNS = 100
    const val MAX_CHARS = 3_000_000
    const val SHEET_LABEL = "Sheet: CSV"

    data class Result(val text: String, val truncated: Boolean)

    fun extract(raw: String): Result {
        val delimiter = detectDelimiter(raw)
        val (rows, truncatedRows) = parse(raw, delimiter)
        val out = StringBuilder()
        out.append('[').append(SHEET_LABEL).append("]\n")
        var truncated = truncatedRows
        for ((rowIndex, row) in rows.withIndex()) {
            if (out.length >= MAX_CHARS) {
                truncated = true
                break
            }
            row.forEachIndexed { columnIndex, cell ->
                val value = cell.replace('\n', ' ').replace('\r', ' ').trim()
                if (value.isNotEmpty()) {
                    out.append(columnName(columnIndex + 1))
                    out.append(rowIndex + 1)
                    out.append(": ")
                    out.append(value)
                    out.append('\t')
                }
            }
            out.append('\n')
        }
        if (truncated) {
            out.append("[Only the first rows of this sheet were read.]\n")
        }
        return Result(out.toString().trimEnd(), truncated || rows.size >= MAX_ROWS)
    }

    /** Picks the most frequent delimiter in the first few lines, ignoring quoted regions. */
    private fun detectDelimiter(raw: String): Char {
        val counts = mapOf(',' to 0, ';' to 0, '\t' to 0).toMutableMap()
        var inQuotes = false
        var lines = 0
        var i = 0
        while (i < raw.length && lines < 5) {
            val c = raw[i]
            when {
                c == '"' -> inQuotes = !inQuotes
                c == '\n' && !inQuotes -> lines++
                !inQuotes && c in counts -> counts[c] = counts.getValue(c) + 1
            }
            i++
        }
        return counts.maxByOrNull { it.value }?.takeIf { it.value > 0 }?.key ?: ','
    }

    private fun parse(raw: String, delimiter: Char): Pair<List<List<String>>, Boolean> {
        val rows = ArrayList<List<String>>(256)
        var row = ArrayList<String>(16)
        val cell = StringBuilder()
        var inQuotes = false
        var i = 0
        while (i < raw.length) {
            val c = raw[i]
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < raw.length && raw[i + 1] == '"') {
                        cell.append('"')
                        i++
                    } else {
                        inQuotes = false
                    }
                } else {
                    cell.append(c)
                }
            } else {
                when (c) {
                    '"' -> inQuotes = true
                    delimiter -> {
                        row.add(cell.toString())
                        cell.setLength(0)
                    }
                    '\r', '\n' -> {
                        if (c == '\r' && i + 1 < raw.length && raw[i + 1] == '\n') i++
                        row.add(cell.toString())
                        cell.setLength(0)
                        if (row.any { it.isNotBlank() }) {
                            rows.add(if (row.size > MAX_COLUMNS) row.subList(0, MAX_COLUMNS) else row)
                            if (rows.size >= MAX_ROWS) return rows to true
                        }
                        row = ArrayList(16)
                    }
                    '\uFEFF' -> Unit
                    else -> if (!c.isISOControl()) cell.append(c)
                }
            }
            i++
        }
        row.add(cell.toString())
        if (row.any { it.isNotBlank() } && rows.size < MAX_ROWS) {
            rows.add(if (row.size > MAX_COLUMNS) row.subList(0, MAX_COLUMNS) else row)
        }
        return rows to false
    }

    /** 1 -> A, 26 -> Z, 27 -> AA. */
    internal fun columnName(index: Int): String {
        var n = index
        val out = StringBuilder()
        while (n > 0) {
            val remainder = (n - 1) % 26
            out.append(('A' + remainder))
            n = (n - 1) / 26
        }
        return if (out.isEmpty()) "A" else out.reverse().toString()
    }
}
