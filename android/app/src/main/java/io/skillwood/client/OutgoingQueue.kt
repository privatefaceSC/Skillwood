package io.skillwood.client

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class OutgoingQueue(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("skillwood_queue", Context.MODE_PRIVATE)

    fun add(p: Payload) {
        val list = peekAll().toMutableList()
        list.add(p)
        while (list.size > MAX_SIZE) list.removeAt(0)
        save(list)
    }

    fun peekAll(): List<Payload> {
        val raw = prefs.getString(KEY, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map {
                val o = arr.getJSONObject(it)
                Payload(
                    sender = o.getString("sender"),
                    text = o.getString("text"),
                    messengerName = o.getString("messenger"),
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun remove(items: List<Payload>) {
        val toRemove = items.toSet()
        val left = peekAll().filterNot { it in toRemove }
        save(left)
    }

    fun size(): Int = peekAll().size

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    private fun save(list: List<Payload>) {
        val arr = JSONArray()
        list.forEach {
            arr.put(JSONObject(mapOf(
                "sender" to it.sender,
                "text" to it.text,
                "messenger" to it.messengerName,
            )))
        }
        prefs.edit().putString(KEY, arr.toString()).apply()
    }

    companion object {
        private const val KEY = "queue"
        const val MAX_SIZE = 200
    }
}
