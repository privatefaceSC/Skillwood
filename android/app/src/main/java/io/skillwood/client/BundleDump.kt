package io.skillwood.client

import android.os.Bundle
import android.os.Parcelable

object BundleDump {

    /** Текстовый дамп Bundle: ключи + типы + значения. Для диагностики. */
    fun describe(bundle: Bundle?, indent: String = ""): String {
        if (bundle == null) return "${indent}(null)"
        val sb = StringBuilder()
        for (key in bundle.keySet()) {
            val v = try { bundle.get(key) } catch (e: Throwable) { "<err: ${e.message}>" }
            sb.append(indent).append(key).append(" :: ")
            describeValue(v, indent, sb)
            sb.append('\n')
        }
        return sb.toString().trimEnd()
    }

    private fun describeValue(v: Any?, indent: String, sb: StringBuilder) {
        when (v) {
            null -> sb.append("(null)")
            is CharSequence -> {
                val s = v.toString()
                sb.append("CharSequence[len=").append(s.length).append("] ")
                sb.append(quote(s))
            }
            is Bundle -> {
                sb.append("Bundle{\n")
                sb.append(describe(v, "$indent  "))
                sb.append('\n').append(indent).append('}')
            }
            is Array<*> -> {
                sb.append(v.javaClass.simpleName).append("[size=").append(v.size).append("]")
                if (v.isNotEmpty()) {
                    sb.append(" {\n")
                    for ((i, el) in v.withIndex()) {
                        sb.append(indent).append("  [").append(i).append("] = ")
                        describeValue(el, "$indent  ", sb)
                        sb.append('\n')
                    }
                    sb.append(indent).append('}')
                }
            }
            is Parcelable -> sb.append("Parcelable<").append(v.javaClass.name).append(">")
            else -> sb.append(v.javaClass.simpleName).append(" ").append(v.toString())
        }
    }

    private fun quote(s: String): String {
        val capped = if (s.length > 8000) s.substring(0, 8000) + "…[truncated]" else s
        return "\"" + capped.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
    }
}
