package com.nativelingo.scoring

/**
 * A minimal JSON reader for the golden fixtures.
 *
 * The production code deliberately parses calibration.json with targeted regex
 * to keep `:core-scoring` stdlib-only, but the golden files are nested
 * (objects inside arrays inside objects) and regex is the wrong tool for them —
 * a `"tags": [...]` array is enough to break a naive object matcher, silently
 * yielding zero matches and a test that asserts nothing. This is ~80 lines and
 * lives only in test sources, so it costs the shipped artifact nothing.
 */
object TestJson {

    fun parse(text: String): Any? = Parser(text).run {
        val v = value()
        skipWs()
        v
    }

    fun obj(text: String): Map<String, Any?> {
        @Suppress("UNCHECKED_CAST")
        return parse(text) as Map<String, Any?>
    }

    private class Parser(val s: String) {
        var i = 0

        fun skipWs() { while (i < s.length && s[i].isWhitespace()) i++ }

        fun value(): Any? {
            skipWs()
            return when (s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> str()
                't' -> { expect("true"); true }
                'f' -> { expect("false"); false }
                'n' -> { expect("null"); null }
                else -> num()
            }
        }

        fun expect(lit: String) {
            require(s.startsWith(lit, i)) { "expected $lit at $i" }
            i += lit.length
        }

        fun obj(): Map<String, Any?> {
            val out = LinkedHashMap<String, Any?>()
            i++ // {
            skipWs()
            if (s[i] == '}') { i++; return out }
            while (true) {
                skipWs()
                val k = str()
                skipWs()
                require(s[i] == ':') { "expected ':' at $i" }
                i++
                out[k] = value()
                skipWs()
                when (s[i]) {
                    ',' -> i++
                    '}' -> { i++; return out }
                    else -> error("expected ',' or '}' at $i")
                }
            }
        }

        fun arr(): List<Any?> {
            val out = ArrayList<Any?>()
            i++ // [
            skipWs()
            if (s[i] == ']') { i++; return out }
            while (true) {
                out.add(value())
                skipWs()
                when (s[i]) {
                    ',' -> i++
                    ']' -> { i++; return out }
                    else -> error("expected ',' or ']' at $i")
                }
            }
        }

        fun str(): String {
            require(s[i] == '"') { "expected string at $i" }
            i++
            val sb = StringBuilder()
            while (s[i] != '"') {
                if (s[i] == '\\') {
                    i++
                    when (val c = s[i]) {
                        'n' -> sb.append('\n'); 't' -> sb.append('\t')
                        'r' -> sb.append('\r'); 'b' -> sb.append('\b')
                        'f' -> sb.append('')
                        'u' -> { sb.append(s.substring(i + 1, i + 5).toInt(16).toChar()); i += 4 }
                        else -> sb.append(c)  // \" \\ \/
                    }
                } else sb.append(s[i])
                i++
            }
            i++
            return sb.toString()
        }

        fun num(): Double {
            val start = i
            while (i < s.length && (s[i].isDigit() || s[i] in "-+.eE")) i++
            return s.substring(start, i).toDouble()
        }
    }
}

// --- typed accessors, so the tests read cleanly -------------------------------

@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.objList(key: String): List<Map<String, Any?>> =
    (this[key] as? List<Any?> ?: emptyList()) as List<Map<String, Any?>>

fun Map<String, Any?>.strList(key: String): List<String> =
    (this[key] as? List<Any?> ?: emptyList()).map { it as String }

fun Map<String, Any?>.str(key: String): String = this[key] as String

fun Map<String, Any?>.f(key: String): Float = (this[key] as Number).toFloat()

fun Map<String, Any?>.fOrNull(key: String): Float? = (this[key] as Number?)?.toFloat()

fun Map<String, Any?>.int(key: String): Int = (this[key] as Number).toInt()
