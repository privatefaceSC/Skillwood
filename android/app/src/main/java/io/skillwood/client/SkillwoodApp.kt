package io.skillwood.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.util.Log
import androidx.work.Configuration
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class SkillwoodApp : Application(), Configuration.Provider {
    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setMinimumLoggingLevel(Log.INFO)
            .build()

    override fun onCreate() {
        super.onCreate()
        ensureNotificationChannel()
        scheduleQueueDrain()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        val foreground = NotificationChannel(
            CHANNEL_FOREGROUND,
            getString(R.string.channel_foreground),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.channel_foreground_desc)
            setShowBadge(false)
        }
        // Канал для full-screen-intent: IMPORTANCE_HIGH обязателен, иначе
        // система не запустит full-screen activity при погашенном экране.
        val wake = NotificationChannel(
            CHANNEL_WAKE,
            getString(R.string.channel_wake),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = getString(R.string.channel_wake_desc)
            setShowBadge(false)
            setSound(null, null)
            enableVibration(false)
            lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
        }
        nm.createNotificationChannel(foreground)
        nm.createNotificationChannel(wake)
    }

    private fun scheduleQueueDrain() {
        val req = PeriodicWorkRequestBuilder<QueueDrainWorker>(15, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "skillwood-queue-drain",
            ExistingPeriodicWorkPolicy.KEEP,
            req,
        )
    }

    companion object {
        const val CHANNEL_FOREGROUND = "skillwood_foreground"
        const val CHANNEL_WAKE = "skillwood_wake"
    }
}
