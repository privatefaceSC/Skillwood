package io.skillwood.client

import android.app.Notification
import android.os.Bundle
import android.os.Parcelable

data class Payload(val sender: String, val text: String, val messengerName: String)

object PayloadExtraction {

    fun fromExtras(extras: Bundle, appName: String, flags: Int): Payload? {
        val ongoing = (flags and Notification.FLAG_ONGOING_EVENT) != 0
        val foreground = (flags and Notification.FLAG_FOREGROUND_SERVICE) != 0
        if (ongoing || foreground) return null

        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty().trim()
        val app = appName.trim()

        // Современные мессенджеры (Telegram, WhatsApp, Signal) используют
        // MessagingStyle: в EXTRA_TEXT лежит усечённое preview с многоточием,
        // а полный текст последнего сообщения — в EXTRA_MESSAGES.
        val messagingStyle = lastMessagingStyleText(extras)
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val textLines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
            ?.lastOrNull()?.toString().orEmpty()
        val plain = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()

        val text = when {
            messagingStyle.isNotBlank() -> messagingStyle
            bigText.isNotBlank() -> bigText
            textLines.isNotBlank() -> textLines
            else -> plain
        }.trim()

        if (title.isBlank() || text.isBlank() || app.isBlank()) return null
        return Payload(sender = title, text = text, messengerName = app)
    }

    @Suppress("DEPRECATION")
    private fun lastMessagingStyleText(extras: Bundle): String {
        val arr: Array<Parcelable> = extras.getParcelableArray(Notification.EXTRA_MESSAGES) ?: return ""
        // Системные уведомления Telegram (закрепление, удаление, «X is typing»)
        // приходят в том же массиве messages с пустым sender, и часто оказываются
        // самыми свежими по времени. Нужно брать последнее «настоящее» сообщение —
        // с непустым sender. Если таких нет — fallback на любое непустое.
        var lastWithSender = ""
        var lastAny = ""
        for (p in arr) {
            if (p !is Bundle) continue
            val text = p.getCharSequence("text")?.toString().orEmpty()
            if (text.isBlank()) continue
            lastAny = text
            val sender = p.getCharSequence("sender")?.toString().orEmpty()
            if (sender.isNotBlank()) lastWithSender = text
        }
        return lastWithSender.ifBlank { lastAny }
    }
}
