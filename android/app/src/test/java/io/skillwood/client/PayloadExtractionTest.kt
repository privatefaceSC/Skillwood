package io.skillwood.client

import android.app.Notification
import android.os.Bundle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class PayloadExtractionTest {

    private fun bundle(title: String? = null, text: String? = null, bigText: String? = null) =
        Bundle().apply {
            title?.let { putCharSequence(Notification.EXTRA_TITLE, it) }
            text?.let { putCharSequence(Notification.EXTRA_TEXT, it) }
            bigText?.let { putCharSequence(Notification.EXTRA_BIG_TEXT, it) }
        }

    @Test
    fun extracts_when_all_fields_present() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "Привет"),
            appName = "Telegram",
            flags = 0,
        )
        assertNotNull(p)
        assertEquals("Иван", p!!.sender)
        assertEquals("Привет", p.text)
        assertEquals("Telegram", p.messengerName)
    }

    @Test
    fun prefers_big_text_when_present() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "коротко", bigText = "длинно полно"),
            appName = "Telegram",
            flags = 0,
        )
        assertEquals("длинно полно", p!!.text)
    }

    @Test
    fun returns_null_when_title_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "", text = "привет"),
            appName = "Telegram",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun returns_null_when_text_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = ""),
            appName = "Telegram",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun returns_null_when_app_name_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "привет"),
            appName = "",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun skips_ongoing_event() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Музыка", text = "играет"),
            appName = "Spotify",
            flags = Notification.FLAG_ONGOING_EVENT,
        )
        assertNull(p)
    }

    @Test
    fun prefers_messaging_style_over_truncated_plain_text() {
        // EXTRA_TEXT часто приходит усечённым системой до ~256 символов с «...»;
        // полный текст лежит в EXTRA_MESSAGES (MessagingStyle).
        val full = "К".repeat(900) + " конец"
        val msg = Bundle().apply { putCharSequence("text", full) }
        val extras = Bundle().apply {
            putCharSequence(Notification.EXTRA_TITLE, "Иван")
            putCharSequence(Notification.EXTRA_TEXT, "К".repeat(250) + "…")
            putParcelableArray(Notification.EXTRA_MESSAGES, arrayOf(msg))
        }
        val p = PayloadExtraction.fromExtras(extras, appName = "Telegram", flags = 0)
        assertEquals(full, p!!.text)
    }

    @Test
    fun ignores_system_messages_with_empty_sender_in_messaging_style() {
        // Telegram кладёт в EXTRA_MESSAGES системные уведомления (pin, удаление и т.п.)
        // с пустым sender и более поздним timestamp, чем у настоящего сообщения.
        val realMessage = Bundle().apply {
            putCharSequence("sender", "Иван")
            putCharSequence("text", "длинный полезный текст")
        }
        val systemNotice = Bundle().apply {
            putCharSequence("sender", "")
            putCharSequence("text", "Иван pinned \"длинный полезный...\"")
        }
        val extras = Bundle().apply {
            putCharSequence(Notification.EXTRA_TITLE, "Иван")
            putCharSequence(Notification.EXTRA_TEXT, "preview")
            putParcelableArray(Notification.EXTRA_MESSAGES, arrayOf(realMessage, systemNotice))
        }
        val p = PayloadExtraction.fromExtras(extras, appName = "Telegram", flags = 0)
        assertEquals("длинный полезный текст", p!!.text)
    }

    @Test
    fun picks_last_message_from_messaging_style() {
        val first = Bundle().apply { putCharSequence("text", "первое") }
        val last = Bundle().apply { putCharSequence("text", "последнее свежее") }
        val extras = Bundle().apply {
            putCharSequence(Notification.EXTRA_TITLE, "Иван")
            putCharSequence(Notification.EXTRA_TEXT, "preview")
            putParcelableArray(Notification.EXTRA_MESSAGES, arrayOf(first, last))
        }
        val p = PayloadExtraction.fromExtras(extras, appName = "Telegram", flags = 0)
        assertEquals("последнее свежее", p!!.text)
    }

    @Test
    fun falls_back_to_text_lines_when_no_messaging_style_or_big_text() {
        val extras = Bundle().apply {
            putCharSequence(Notification.EXTRA_TITLE, "Иван")
            putCharSequence(Notification.EXTRA_TEXT, "preview")
            putCharSequenceArray(
                Notification.EXTRA_TEXT_LINES,
                arrayOf<CharSequence>("старая строка", "свежая полная строка"),
            )
        }
        val p = PayloadExtraction.fromExtras(extras, appName = "Mail", flags = 0)
        assertEquals("свежая полная строка", p!!.text)
    }

    @Test
    fun skips_group_summary() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "VK", text = "3 непрочитанных диалога"),
            appName = "VK",
            flags = Notification.FLAG_GROUP_SUMMARY,
        )
        assertNull(p)
    }

    @Test
    fun skips_foreground_service() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Сервис", text = "запущен"),
            appName = "AnyApp",
            flags = Notification.FLAG_FOREGROUND_SERVICE,
        )
        assertNull(p)
    }
}
