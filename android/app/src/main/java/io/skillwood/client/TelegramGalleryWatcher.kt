package io.skillwood.client

import android.content.Context
import android.os.Environment
import android.os.FileObserver
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/**
 * Telegram не кладёт медиа в уведомление (reduced.images=true). Но всё принятое
 * фото/видео он сам пишет в СВОЮ медиапапку:
 *   Android/media/org.telegram.messenger/Telegram/Telegram Images|Video
 * (а НЕ в Pictures/Telegram — туда копия попадает только при включённой в
 * Telegram настройке «Сохранять в галерею»; обычно она выключена, поэтому
 * раньше watcher смотрел в пустые Pictures/Telegram и ничего не находил).
 * Папка Android/media/<pkg> читается приложению с MANAGE_EXTERNAL_STORAGE.
 *
 * ВАЖНО: это ПЕРВИЧНОЕ хранилище Telegram, а не копия — файлы НЕ удаляем,
 * иначе фото пропадёт и в самом Telegram. Только пересылаем и помечаем dedup;
 * кэш Telegram чистит сам по своему лимиту.
 *
 * Схема:
 *  - файл (новый через FileObserver ИЛИ найденный сканом) матчим к ближайшему
 *    по времени Telegram-уведомлению (очередь sender+ts в SkillwoodListener) →
 *    знаем отправителя → шлём на сайт этому контакту, помечаем отправленным;
 *  - файлы без матча не трогаем — придёт уведомление, добор подхватит;
 *  - скан на старте и по каждому Telegram-уведомлению добирают то, что
 *    FileObserver на FUSE-смонтированном /sdcard пропустил (события чужих
 *    приложений теряются) или что появилось, пока процесс был убит.
 */
class TelegramGalleryWatcher(
    private val context: Context,
    private val settings: SettingsRepository,
    private val apiClient: ApiClient,
    private val scope: CoroutineScope,
    private val recentSenders: () -> List<Pair<String, Long>>,
) {
    private val ext = Environment.getExternalStorageDirectory()

    // Основной путь — собственные папки Telegram. Запасной — Pictures/Movies
    // на случай, если у пользователя включено «Сохранять в галерею».
    private val watchedDirs = listOf(
        File(ext, "Android/media/org.telegram.messenger/Telegram/Telegram Images"),
        File(ext, "Android/media/org.telegram.messenger/Telegram/Telegram Video"),
        File(ext, "Pictures/Telegram"),
        File(ext, "Movies/Telegram"),
    )

    private val observers = mutableListOf<FileObserver>()
    private val observedPaths = HashSet<String>()
    @Volatile private var lastRescan = 0L
    @Volatile private var running = false

    // Атомарная защита от дубля: FileObserver шлёт CLOSE_WRITE и MOVED_TO на
    // один файл, плюс параллельный скан — не должны пройти дедуп дважды.
    private val inFlightLock = Any()
    private val inFlight = HashSet<String>()

    private fun claim(key: String): Boolean = synchronized(inFlightLock) {
        if (inFlight.contains(key)) false else { inFlight.add(key); true }
    }

    private fun release(key: String) = synchronized(inFlightLock) { inFlight.remove(key) }

    fun start() {
        if (running) return
        running = true
        ensureObservers()
        scope.launch { rescan(force = true) }
        // Периодический добор: не зависим ни от FileObserver (на FUSE он
        // теряет события чужих приложений), ни от прихода уведомлений.
        scope.launch {
            while (running && isActive) {
                delay(PERIODIC_RESCAN_MS)
                ensureObservers()
                rescan()
            }
        }
    }

    /**
     * Вызывается на каждом Telegram-уведомлении: файл мог уже сохраниться,
     * а FileObserver его пропустить; заодно подцепляем папки, которых на
     * старте ещё не было (Telegram создаёт их при первом сохранении).
     */
    fun nudge() {
        scope.launch {
            ensureObservers()
            rescan()
        }
    }

    fun stop() {
        running = false
        observers.forEach { it.stopWatching() }
        observers.clear()
        synchronized(observedPaths) { observedPaths.clear() }
    }

    /** Идемпотентно вешает FileObserver на существующие, ещё не наблюдаемые папки. */
    private fun ensureObservers() {
        for (dir in watchedDirs) {
            val path = dir.absolutePath
            synchronized(observedPaths) {
                if (observedPaths.contains(path)) return@synchronized
                if (!dir.isDirectory) {
                    Log.d(TAG, "папки пока нет: $path")
                    return@synchronized
                }
                @Suppress("DEPRECATION")
                val obs = object : FileObserver(path, CLOSE_WRITE or MOVED_TO) {
                    override fun onEvent(event: Int, name: String?) {
                        if (name == null) return
                        Log.d(TAG, "event=$event file=$name dir=${dir.name}")
                        scope.launch { handleFile(File(dir, name)) }
                    }
                }
                obs.startWatching()
                observers.add(obs)
                observedPaths.add(path)
                Log.d(TAG, "watching $path")
            }
        }
    }

    private suspend fun handleFile(f: File) {
        val name = f.name
        if (name.startsWith(".")) return                 // .trashed-/.pending-/.nomedia
        val typed = classify(name) ?: run { Log.d(TAG, "skip not-media: $name"); return }
        val (mime, kind) = typed
        val dedup = "tg:$name"
        if (settings.wasMediaSent(dedup)) return
        if (!f.exists() || f.length() == 0L) { Log.d(TAG, "skip empty/missing: $name"); return }
        // Файл мог ещё докачиваться (медленный VPN) — берём только «устоявшийся».
        if (System.currentTimeMillis() - f.lastModified() < SETTLE_MS) {
            Log.d(TAG, "skip ещё пишется: $name"); return
        }

        val sender = matchSender(f.lastModified())
        if (sender == null) {
            Log.d(TAG, "no sender match for $name (mtime=${f.lastModified()}, " +
                "senders=${recentSenders().size}) — не трогаем, ждём уведомления")
            return
        }
        if (!claim(dedup)) { Log.d(TAG, "skip in-flight dup: $name"); return }
        try {
            val bytes = try {
                f.readBytes()
            } catch (e: Throwable) {
                Log.w(TAG, "read failed ${f.name}: ${e.message}"); return
            }
            Log.d(TAG, "sending $name kind=$kind sender=$sender size=${bytes.size}")
            when (apiClient.sendMedia(sender, "Telegram", kind, dedup, bytes, mime)) {
                is Result.Success -> {
                    settings.markMediaSent(dedup)
                    settings.recordSuccess()
                    // Файл НЕ удаляем — это хранилище самого Telegram.
                    Log.d(TAG, "OK sent $name (файл оставлен)")
                }
                is Result.Error -> {
                    settings.recordError()  // повторим на следующем доборе
                    Log.w(TAG, "send failed $name — повтор позже")
                }
            }
        } finally {
            release(dedup)
        }
    }

    /**
     * Отправитель файла = ближайшее Telegram-уведомление, пришедшее НЕ ПОЗЖЕ
     * файла (Telegram создаёт файл уже ПОСЛЕ показа уведомления; PRE_SLACK_MS —
     * запас на дрожание часов/порядок событий). Направленность критична: иначе
     * накопившийся бэклог старых файлов «прилипает» к первому же свежему
     * уведомлению и улетает не тому контакту (баг 2026-05-16).
     */
    private fun matchSender(fileTime: Long): String? {
        var best: String? = null
        var bestScore = Long.MAX_VALUE
        for ((sender, ts) in recentSenders()) {
            val delta = fileTime - ts                 // >0: файл появился после уведомления
            if (delta < -PRE_SLACK_MS) continue        // уведомление позже файла — не его
            if (delta > MATCH_WINDOW_MS) continue      // слишком давно — не его
            val score = kotlin.math.abs(delta)
            if (score < bestScore) { bestScore = score; best = sender }
        }
        return best
    }

    /**
     * Добор: FileObserver на FUSE-смонтированном /sdcard теряет события для
     * файлов, которые пишет другое приложение (Telegram), плюс процесс мог
     * быть убит, пока шла докачка. Поэтому периодически сами пересматриваем
     * недавние файлы. Ничего не удаляем — только пересылаем неотправленные
     * с матчем по отправителю.
     */
    private suspend fun rescan(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - lastRescan < RESCAN_THROTTLE_MS) return
        lastRescan = now
        for (dir in watchedDirs) {
            val files = dir.listFiles() ?: continue
            for (f in files) {
                if (!f.isFile || f.name.startsWith(".")) continue
                if (classify(f.name) == null) continue
                if (now - f.lastModified() > MATCH_WINDOW_MS) continue   // старше окна — матча уже не будет
                if (settings.wasMediaSent("tg:${f.name}")) continue
                handleFile(f)
            }
        }
    }

    /** (mime, kind) для фото/видео, либо null если не наш тип. */
    private fun classify(name: String): Pair<String, String>? {
        val n = name.lowercase()
        return when {
            n.endsWith(".jpg") || n.endsWith(".jpeg") -> "image/jpeg" to "image"
            n.endsWith(".png") -> "image/png" to "image"
            n.endsWith(".webp") -> "image/webp" to "image"
            // Telegram иногда сохраняет видео как .mp4.mov / .mov / .MOV.
            n.endsWith(".mp4") || n.endsWith(".mov") ||
                n.endsWith(".mkv") || n.endsWith(".webm") || n.contains(".mp4") ->
                "video/mp4" to "video"
            else -> null
        }
    }

    companion object {
        private const val TAG = "SkillwoodTG"
        // Окно матча файл↔уведомление с запасом под медленный VPN (Telegram в РФ).
        private const val MATCH_WINDOW_MS = 1_200_000L   // 20 мин: файл ПОСЛЕ уведомления
        private const val PRE_SLACK_MS = 120_000L        // запас, если файл чуть раньше уведомления
        private const val RESCAN_THROTTLE_MS = 60_000L   // добор не чаще раза в минуту
        private const val PERIODIC_RESCAN_MS = 90_000L   // тик таймера-добора (> throttle)
        private const val SETTLE_MS = 4_000L             // файл «устоялся» (докачка завершена)
    }
}
