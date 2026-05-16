package io.skillwood.client

import android.app.Notification
import android.os.Bundle
import android.os.Parcelable

data class Payload(val sender: String, val text: String, val messengerName: String)

/** Ссылка на медиа-вложение из уведомления. dedupKey стабилен между
 *  повторными накопительными уведомлениями (у Max/VK это сам content-Uri). */
data class MediaRef(
    val uriString: String,
    val mime: String?,
    val dedupKey: String,
    val sender: String,
    val kind: String,
)

object PayloadExtraction {

    /**
     * Вложения-картинки из MessagingStyle (Max/VK кладут content://-Uri фото
     * с image-mime прямо в сообщение). Telegram сюда ничего не кладёт —
     * вернётся пустой список, это нормально.
     */
    @Suppress("DEPRECATION")
    fun imageRefs(extras: Bundle): List<MediaRef> {
        val arr: Array<Parcelable> = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
            ?: return emptyList()
        val titleFallback = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val out = ArrayList<MediaRef>()
        val seen = HashSet<String>()
        for (p in arr) {
            if (p !is Bundle) continue
            val uri = p.get("uri") ?: continue
            val mime = p.getCharSequence("type")?.toString()
            if (mime == null || !mime.startsWith("image/")) continue
            val uriString = uri.toString()
            if (uriString.isBlank() || !seen.add(uriString)) continue
            val sender = p.getCharSequence("sender")?.toString()
                ?.takeIf { it.isNotBlank() } ?: titleFallback
            if (sender.isBlank()) continue
            // Max отдаёт стикеры/смайлы тем же image-mime, но с getSmile в Uri.
            val kind = if (uriString.contains("getSmile")) "sticker" else "image"
            out.add(MediaRef(uriString = uriString, mime = mime,
                             dedupKey = uriString, sender = sender, kind = kind))
        }
        return out
    }

    fun fromExtras(extras: Bundle, appName: String, flags: Int): Payload? {
        val ongoing = (flags and Notification.FLAG_ONGOING_EVENT) != 0
        val foreground = (flags and Notification.FLAG_FOREGROUND_SERVICE) != 0
        // Сводка группы («3 непрочитанных диалога», «4 сообщения») — это
        // обёртка, а не само сообщение. У реальных уведомлений этого флага нет.
        val groupSummary = (flags and Notification.FLAG_GROUP_SUMMARY) != 0
        if (ongoing || foreground || groupSummary) return null

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

    /**
     * Последнее сообщение MessagingStyle (с непустым sender), текст которого НЕ
     * отброшен [exclude]. Нужно для Telegram: в одном уведомлении копятся и
     * медиа-заглушки («Фотография»), и реальный текст — нельзя терять текст
     * только потому, что последним оказалось фото. null если реального текста нет.
     */
    @Suppress("DEPRECATION")
    fun lastTextExcluding(extras: Bundle, exclude: (String) -> Boolean): String? {
        val arr: Array<Parcelable> = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
            ?: return null
        var result: String? = null
        for (p in arr) {
            if (p !is Bundle) continue
            val text = p.getCharSequence("text")?.toString()?.trim().orEmpty()
            if (text.isBlank()) continue
            val sender = p.getCharSequence("sender")?.toString().orEmpty()
            if (sender.isBlank()) continue
            if (exclude(text)) continue
            result = text
        }
        return result
    }

    /** Есть ли в MessagingStyle хоть одно сообщение (с непустым sender),
     *  текст которого удовлетворяет [predicate]. Для детекта медиа в Telegram. */
    @Suppress("DEPRECATION")
    fun anyMessageText(extras: Bundle, predicate: (String) -> Boolean): Boolean {
        val arr: Array<Parcelable> = extras.getParcelableArray(Notification.EXTRA_MESSAGES)
            ?: return false
        for (p in arr) {
            if (p !is Bundle) continue
            val text = p.getCharSequence("text")?.toString()?.trim().orEmpty()
            if (text.isBlank()) continue
            val sender = p.getCharSequence("sender")?.toString().orEmpty()
            if (sender.isBlank()) continue
            if (predicate(text)) return true
        }
        return false
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
