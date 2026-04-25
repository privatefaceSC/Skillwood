package io.skillwood.client

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.app.Service
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val tap = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val n: Notification = NotificationCompat.Builder(this, SkillwoodApp.CHANNEL_FOREGROUND)
            .setContentTitle(getString(R.string.foreground_title))
            .setContentText(getString(R.string.foreground_text))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .setContentIntent(tap)
            .build()
        startForeground(NOTIFICATION_ID, n)
        return START_STICKY
    }

    companion object {
        private const val NOTIFICATION_ID = 1001
        fun start(ctx: Context) {
            val i = Intent(ctx, ForegroundService::class.java)
            ctx.startForegroundService(i)
        }
        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, ForegroundService::class.java))
        }
    }
}
