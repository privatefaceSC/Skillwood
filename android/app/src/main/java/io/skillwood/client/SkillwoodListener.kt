package io.skillwood.client

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SkillwoodListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private lateinit var settings: SettingsRepository
    private lateinit var apiClient: ApiClient
    private lateinit var queue: OutgoingQueue
    private var tgWatcher: TelegramGalleryWatcher? = null

    override fun onCreate() {
        super.onCreate()
        settings = SettingsRepository(this)
        apiClient = ApiClient(settings)
        queue = OutgoingQueue(this)
        maybeStartTelegramWatcher()
    }

    override fun onDestroy() {
        tgWatcher?.stop()
        super.onDestroy()
    }

    override fun onListenerConnected() {
        Log.d(TAG, "onListenerConnected — listener привязан, уведомления пойдут")
        maybeStartTelegramWatcher()
    }

    override fun onListenerDisconnected() {
        Log.w(TAG, "onListenerDisconnected — listener ОТВЯЗАН, уведомления НЕ идут")
    }

    /**
     * Старт watcher устойчив к порядку выдачи разрешений и переустановкам:
     * пробуем и в onCreate, и лениво на каждом уведомлении, пока не поднимется.
     */
    private fun maybeStartTelegramWatcher() {
        if (tgWatcher != null) return
        val canManageFiles = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
            Environment.isExternalStorageManager()
        if (!canManageFiles) {
            Log.w(TAG, "watcher не стартует: нет доступа ко всем файлам")
            return
        }
        tgWatcher = TelegramGalleryWatcher(
            applicationContext, settings, apiClient, scope,
        ) { recentTelegramSenders() }.also { it.start() }
        Log.d(TAG, "TelegramGalleryWatcher запущен")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        // ДИАГНОСТИКА: видим КАЖДОЕ уведомление — доходит ли вообще и от кого.
        Log.d(TAG, "onPosted pkg=${sbn.packageName}")
        if (!settings.isConfigured()) { Log.d(TAG, "  пропуск: не сконфигурирован"); return }
        maybeStartTelegramWatcher()  // лениво поднимаем, если ещё не стартовал
        if (!NotificationFilter.shouldForward(
                sbn.packageName,
                applicationContext.packageName,
                settings.allowedPackages)) {
            Log.d(TAG, "  пропуск: не в whitelist (${sbn.packageName})")
            return
        }

        val appName = try {
            val info = packageManager.getApplicationInfo(sbn.packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (_: Exception) {
            sbn.packageName
        }

        // Telegram медиа в уведомление не кладёт — но имя отправителя есть.
        // Запоминаем его, чтобы TelegramGalleryWatcher привязал к нему файл,
        // который Telegram сохранит в галерею чуть позже.
        if (sbn.packageName == TELEGRAM_PKG) {
            val title = sbn.notification.extras
                .getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim().orEmpty()
            if (title.isNotEmpty()) {
                rememberTelegramSender(title, System.currentTimeMillis())
            }
            // Файл мог уже сохраниться в медиапапку Telegram, а FileObserver
            // на FUSE его пропустить — подталкиваем добор именно сейчас, когда
            // только что запомнили отправителя.
            tgWatcher?.nudge()
        }

        // Если в уведомлении есть фото (Max/VK кладут content://-Uri) — шлём
        // медиа отдельным запросом; сервер сам создаёт сообщение с картинкой,
        // поэтому текстовую заглушку («📷 фото») в этом случае не дублируем.
        val refs = PayloadExtraction.imageRefs(sbn.notification.extras)
        if (refs.isNotEmpty()) {
            scope.launch { sendMediaRefs(appName, refs) }
            return
        }

        val payload = PayloadExtraction.fromExtras(
            extras = sbn.notification.extras,
            appName = appName,
            flags = sbn.notification.flags,
        ) ?: return

        // Telegram через прокси в фоне медиа не качает — если в уведомлении есть
        // признак медиа, на пару секунд поднимаем Telegram, чтобы он докачал
        // и сохранил файл в галерею (его подхватит watcher).
        if (sbn.packageName == TELEGRAM_PKG &&
            (isTelegramMediaPlaceholder(payload.text) ||
                PayloadExtraction.anyMessageText(sbn.notification.extras) {
                    isTelegramMediaPlaceholder(it)
                })
        ) {
            // contentIntent уведомления открывает ИМЕННО этот чат (как твой
            // тап по уведомлению) — Telegram в открытом чате докачивает медиа.
            maybeWakeForTelegram(sbn.notification.contentIntent)
        }

        // Telegram копит в одном уведомлении и медиа-заглушки («Фотография»),
        // и реальный текст. Нельзя терять текст только из-за того, что ПОСЛЕДНИМ
        // оказалось фото: фильтруем заглушки по каждому сообщению и берём
        // последний реальный текст. Сами файлы придут через watcher.
        if (sbn.packageName == TELEGRAM_PKG && isTelegramMediaPlaceholder(payload.text)) {
            val realText = PayloadExtraction.lastTextExcluding(sbn.notification.extras) {
                isTelegramMediaPlaceholder(it)
            }
            if (realText.isNullOrBlank()) {
                Log.d(TAG, "tg: только медиа-заглушки — не шлём текстом, ждём watcher")
                return
            }
            Log.d(TAG, "tg: отделили реальный текст от медиа-заглушек")
            scope.launch { sendOrEnqueue(payload.copy(text = realText)) }
            return
        }

        scope.launch { sendOrEnqueue(payload) }
    }

    private suspend fun sendOrEnqueue(p: Payload) {
        when (val r = apiClient.sendNotification(p.sender, p.text, p.messengerName)) {
            is Result.Success -> {
                settings.recordSuccess()
                broadcastStats()
                drainQueue()
            }
            is Result.Error -> when (r.kind) {
                Result.ErrorKind.Network, Result.ErrorKind.Server, Result.ErrorKind.Unknown -> {
                    queue.add(p)
                    settings.recordError()
                    broadcastStats()
                }
                Result.ErrorKind.Unauthorized -> handleUnauthorized(p)
                Result.ErrorKind.BadRequest, Result.ErrorKind.NotFound -> {
                    settings.recordError()
                    broadcastStats()
                }
            }
        }
    }

    /**
     * Фото из уведомления: лучшее-усилие. В персистентную очередь не кладём
     * (объёмно для SharedPreferences) — при сетевом сбое фото просто потеряется,
     * текстовый канал при этом продолжает работать штатно.
     */
    private suspend fun sendMediaRefs(messenger: String, refs: List<MediaRef>) {
        for (ref in refs) {
            if (settings.wasMediaSent(ref.dedupKey)) continue
            val bytes = readUri(ref.uriString) ?: continue
            when (val r = apiClient.sendMedia(
                ref.sender, messenger, ref.kind, ref.dedupKey, bytes, ref.mime)) {
                is Result.Success -> {
                    settings.markMediaSent(ref.dedupKey)
                    settings.recordSuccess()
                    broadcastStats()
                }
                is Result.Error -> {
                    if (r.kind == Result.ErrorKind.Unauthorized) {
                        Log.w(TAG, "media 401 from server")
                    }
                    settings.recordError()
                    broadcastStats()
                }
            }
        }
    }

    private fun readUri(uriString: String): ByteArray? = try {
        applicationContext.contentResolver
            .openInputStream(Uri.parse(uriString))?.use { it.readBytes() }
    } catch (e: Throwable) {
        Log.w(TAG, "readUri failed: ${e.message}")
        null
    }

    /**
     * Не выкидываем пользователя с одного 401: кладём payload в очередь и считаем
     * подряд идущие 401. Wipe токена делаем только когда подряд накопилось
     * [UNAUTH_STREAK_THRESHOLD] — это защищает от случайных 401 (засыпание сервера,
     * captive portal, чужой сервис на том же порту, временные сетевые артефакты).
     */
    private fun handleUnauthorized(p: Payload) {
        queue.add(p)
        val streak = settings.recordUnauthorized()
        Log.w(TAG, "got 401 from server, streak=$streak/$UNAUTH_STREAK_THRESHOLD")
        if (streak >= UNAUTH_STREAK_THRESHOLD) {
            Log.w(TAG, "unauth streak reached threshold, clearing auth and requesting re-connect")
            settings.clearAuth()
            sendBroadcast(Intent(ACTION_LOGOUT).setPackage(packageName))
        } else {
            broadcastStats()
        }
    }

    private suspend fun drainQueue() {
        val pending = queue.peekAll()
        if (pending.isEmpty()) return
        val sent = mutableListOf<Payload>()
        for (p in pending) {
            val r = apiClient.sendNotification(p.sender, p.text, p.messengerName)
            if (r is Result.Success) {
                sent.add(p); settings.recordSuccess()
            } else break
        }
        if (sent.isNotEmpty()) {
            queue.remove(sent)
            broadcastStats()
        }
    }

    private fun broadcastStats() {
        sendBroadcast(Intent(ACTION_STATS).setPackage(packageName))
    }

    /** Текст Telegram-уведомления — это просто метка медиа («Фотография» и т.п.),
     *  а не настоящее сообщение. Эвристика, зависит от языка Telegram. */
    private fun isTelegramMediaPlaceholder(text: String): Boolean {
        val t = text.trim().lowercase()
        return t in TG_MEDIA_PLACEHOLDERS
    }

    /**
     * Поднять Telegram на пару секунд (через WakeActivity), чтобы он докачал
     * медиа. С троттлингом: несколько фото подряд = один подъём.
     *
     * На Android 14 + HyperOS прямой startActivity из фона при погашенном
     * экране режется BAL. Системно-санкционированный путь — full-screen-intent
     * уведомление (как входящий звонок): систему просим сама поднять
     * WakeActivity. Прямой startActivity пробуем тоже — он мгновенный, когда
     * экран включён и запуск разрешён.
     */
    private fun maybeWakeForTelegram(chatIntent: PendingIntent?) {
        val now = System.currentTimeMillis()
        synchronized(wakeGate) {
            if (now - lastWakeAt < WAKE_THROTTLE_MS) return
            lastWakeAt = now
        }

        val wakeIntent = Intent(this, WakeActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            putExtra(WakeActivity.EXTRA_SECONDS, WakeActivity.DEFAULT_SECONDS)
            if (chatIntent != null) putExtra(WakeActivity.EXTRA_CHAT_INTENT, chatIntent)
        }

        // 1) Full-screen-intent — надёжный путь при погашенном/заблокированном
        //    экране (систему просим поднять activity сама).
        val piFlags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val fsiPi = PendingIntent.getActivity(this, WAKE_REQ, wakeIntent, piFlags)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val nm = getSystemService(NotificationManager::class.java)
            if (!nm.canUseFullScreenIntent()) {
                Log.w(TAG, "USE_FULL_SCREEN_INTENT НЕ выдан — система не поднимет " +
                    "Telegram с погашенного экрана (кнопка в приложении)")
            }
        }
        try {
            val n = NotificationCompat.Builder(this, SkillwoodApp.CHANNEL_WAKE)
                .setSmallIcon(applicationInfo.icon)
                .setContentTitle(getString(R.string.wake_title))
                .setContentText(getString(R.string.wake_text))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_CALL)
                .setOngoing(false)
                .setAutoCancel(true)
                .setTimeoutAfter((WakeActivity.DEFAULT_SECONDS + 5) * 1000L)
                .setContentIntent(fsiPi)
                .setFullScreenIntent(fsiPi, true)
                .build()
            getSystemService(NotificationManager::class.java)
                .notify(WakeActivity.NOTIF_ID, n)
            Log.d(TAG, "FSI-уведомление выставлено (чат из уведомления=${chatIntent != null})")
        } catch (e: Throwable) {
            Log.w(TAG, "FSI notify failed: ${e.message}")
        }

        // 2) Прямой запуск — мгновенный, когда экран включён и BAL разрешает.
        try {
            startActivity(wakeIntent)
            Log.d(TAG, "прямой startActivity WakeActivity отправлен")
        } catch (e: Throwable) {
            Log.d(TAG, "прямой startActivity заблокирован (ждём FSI): ${e.message}")
        }
    }

    companion object {
        private const val TAG = "Skillwood"
        private const val TELEGRAM_PKG = "org.telegram.messenger"
        const val ACTION_STATS = "io.skillwood.client.STATS"
        const val ACTION_LOGOUT = "io.skillwood.client.LOGOUT"
        const val UNAUTH_STREAK_THRESHOLD = 5

        // id FSI-уведомления — общий с WakeActivity (WakeActivity.NOTIF_ID).
        private const val WAKE_REQ = 7001

        // Троттлинг подъёма Telegram: серия фото подряд = один подъём.
        private const val WAKE_THROTTLE_MS = 25_000L
        private val wakeGate = Any()
        @Volatile private var lastWakeAt = 0L

        private val TG_MEDIA_PLACEHOLDERS = setOf(
            "фотография", "фото", "видео", "видеосообщение", "видеосообщение 🎥",
            "голосовое сообщение", "голосовое", "gif", "гиф", "анимация",
            "стикер", "документ", "файл", "аудио", "музыка",
            "photo", "video", "video message", "voice message", "voice",
            "sticker", "document", "file", "audio", "animation",
        )

        // Очередь недавних Telegram-отправителей для привязки файлов из галереи.
        // Должна жить дольше окна матча watcher'а (медленный VPN).
        private const val TG_RETENTION_MS = 2_100_000L
        private val tgLock = Any()
        private val tgSenders = ArrayList<Pair<String, Long>>()

        fun rememberTelegramSender(sender: String, ts: Long) {
            synchronized(tgLock) {
                tgSenders.add(sender to ts)
                val cutoff = ts - TG_RETENTION_MS
                tgSenders.removeAll { it.second < cutoff }
                while (tgSenders.size > 50) tgSenders.removeAt(0)
            }
        }

        fun recentTelegramSenders(): List<Pair<String, Long>> =
            synchronized(tgLock) { ArrayList(tgSenders) }
    }
}
