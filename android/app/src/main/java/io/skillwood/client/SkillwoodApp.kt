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
        val ch = NotificationChannel(
            CHANNEL_FOREGROUND,
            getString(R.string.channel_foreground),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.channel_foreground_desc)
            setShowBadge(false)
        }
        nm.createNotificationChannel(ch)
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
    }
}
