package io.skillwood.client

import android.app.Activity
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.WindowManager

/**
 * Невидимая activity, которую listener поднимает, когда в Telegram пришло медиа.
 * Будит экран поверх (незащищённого) локскрина, на несколько секунд выводит
 * Telegram на передний план — он докачивает медиа и с настройкой «Сохранять
 * в галерею» кладёт файл в Pictures/Telegram, который ловит TelegramGalleryWatcher.
 * Затем сворачивает всё (home) и закрывается. Экран гаснет сам по системному
 * таймауту — приложение не может выключить его принудительно.
 */
class WakeActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Подняты (FSI или прямым запуском) — гасим триггер-уведомление.
        try {
            getSystemService(NotificationManager::class.java)?.cancel(NOTIF_ID)
        } catch (_: Throwable) { /* не критично */ }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                    WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
            )
        }

        val seconds = intent.getIntExtra(EXTRA_SECONDS, DEFAULT_SECONDS)
            .coerceIn(2, 30)

        @Suppress("DEPRECATION")
        val chatIntent: PendingIntent? = intent.getParcelableExtra(EXTRA_CHAT_INTENT)
        val opened = if (chatIntent != null) {
            // Открыть ИМЕННО нужный чат (как тап по уведомлению) — в открытом
            // чате Telegram докачивает медиа и сохраняет в галерею.
            try {
                chatIntent.send()
                Log.d(TAG, "открыт чат через contentIntent на ${seconds}s")
                true
            } catch (e: Throwable) {
                Log.w(TAG, "contentIntent.send failed: ${e.message}")
                false
            }
        } else false

        if (!opened) {
            val tg = packageManager.getLaunchIntentForPackage(TELEGRAM_PKG)
            if (tg == null) {
                Log.w(TAG, "Telegram не установлен — нечего поднимать")
                finish()
                return
            }
            tg.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            try {
                startActivity(tg)
                Log.d(TAG, "Telegram (главный экран) поднят на ${seconds}s")
            } catch (e: Throwable) {
                Log.w(TAG, "не удалось поднять Telegram: ${e.message}")
                finish()
                return
            }
        }

        Handler(Looper.getMainLooper()).postDelayed({
            try {
                startActivity(Intent(Intent.ACTION_MAIN).apply {
                    addCategory(Intent.CATEGORY_HOME)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                })
            } catch (_: Throwable) { /* не критично */ }
            finish()
        }, seconds * 1000L)
    }

    companion object {
        private const val TAG = "SkillwoodWake"
        private const val TELEGRAM_PKG = "org.telegram.messenger"
        const val EXTRA_CHAT_INTENT = "chat_intent"
        const val EXTRA_SECONDS = "seconds"
        const val DEFAULT_SECONDS = 30
        // id триггер-уведомления (FSI). foreground-сервис = 1001 — не пересекаем.
        const val NOTIF_ID = 2001
    }
}
