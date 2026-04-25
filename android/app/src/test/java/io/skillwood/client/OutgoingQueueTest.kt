package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class OutgoingQueueTest {

    private lateinit var q: OutgoingQueue

    @Before
    fun setUp() {
        q = OutgoingQueue(ApplicationProvider.getApplicationContext())
        q.clear()
    }

    @Test
    fun add_and_peek() {
        q.add(Payload("a", "1", "Telegram"))
        q.add(Payload("b", "2", "MAX"))
        val all = q.peekAll()
        assertEquals(2, all.size)
        assertEquals("a", all[0].sender)
        assertEquals("b", all[1].sender)
    }

    @Test
    fun remove_drops_specified_items() {
        val p1 = Payload("a", "1", "Telegram")
        val p2 = Payload("b", "2", "MAX")
        q.add(p1); q.add(p2)
        q.remove(listOf(p1))
        val all = q.peekAll()
        assertEquals(1, all.size)
        assertEquals("b", all[0].sender)
    }

    @Test
    fun fifo_when_overflow() {
        repeat(205) { i ->
            q.add(Payload("s$i", "t$i", "M"))
        }
        val all = q.peekAll()
        assertEquals(200, all.size)
        assertEquals("s5", all.first().sender)
        assertEquals("s204", all.last().sender)
    }

    @Test
    fun roundtrip_serialization_preserves_unicode() {
        q.add(Payload("Иван", "привет 🚀", "Telegram"))
        val parsed = OutgoingQueue(ApplicationProvider.getApplicationContext()).peekAll()
        assertEquals(1, parsed.size)
        assertEquals("Иван", parsed[0].sender)
        assertEquals("привет 🚀", parsed[0].text)
    }
}
