package com.ashura.tutor.domain.export

/** Minimal, dependency-free JSON writer for the data export (spec §15.3). Pretty-printed, insertion-ordered, strictly valid. */
object Json {
    fun write(value: Any?): String = StringBuilder().also { write(it, value, 0) }.append('\n').toString()

    private fun write(sb: StringBuilder, v: Any?, level: Int) {
        when (v) {
            null -> sb.append("null")
            is String -> quote(sb, v)
            is Boolean -> sb.append(v.toString())
            is Int, is Long -> sb.append(v.toString())
            is Double -> { require(v.isFinite()) { "JSON cannot represent NaN or Infinity" }; sb.append(if (v == Math.rint(v) && Math.abs(v) < 1e15) v.toLong().toString() else v.toString()) }
            is Map<*, *> -> {
                if (v.isEmpty()) { sb.append("{}"); return }
                sb.append("{\n")
                var first = true
                for ((k, x) in v) {
                    require(k is String) { "JSON object keys must be strings" }
                    if (!first) sb.append(",\n"); first = false
                    indent(sb, level + 1); quote(sb, k); sb.append(": "); write(sb, x, level + 1)
                }
                sb.append('\n'); indent(sb, level); sb.append('}')
            }
            is List<*> -> {
                if (v.isEmpty()) { sb.append("[]"); return }
                sb.append("[\n")
                v.forEachIndexed { i, x -> if (i > 0) sb.append(",\n"); indent(sb, level + 1); write(sb, x, level + 1) }
                sb.append('\n'); indent(sb, level); sb.append(']')
            }
            else -> throw IllegalArgumentException("Unsupported JSON type: ${v::class.simpleName}")
        }
    }

    private fun indent(sb: StringBuilder, level: Int) { repeat(level) { sb.append("  ") } }

    private fun quote(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when {
                c == '"' -> sb.append("\\\"")
                c == '\\' -> sb.append("\\\\")
                c == '\n' -> sb.append("\\n")
                c == '\r' -> sb.append("\\r")
                c == '\t' -> sb.append("\\t")
                c == '\b' -> sb.append("\\b")
                c == '\u000C' -> sb.append("\\f")
                c < ' ' || c == '\u2028' || c == '\u2029' || c == '\u007F' -> sb.append("\\u%04x".format(c.code))
                else -> sb.append(c)
            }
        }
        sb.append('"')
    }
}
