package io.skillwood.client

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SkillwoodListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private lateinit var settings: SettingsRepository
    private lateinit var apiClient: ApiClient
    private lateinit var queue: OutgoingQueue

    override fun onCreate() {
        super.onCreate()
        settings = SettingsRepository(this)
        apiClient = ApiClient(settings)
        queue = OutgoingQueue(this)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == applicationContext.packageName) return
        if (!settings.isConfigured()) return

        val appName = try {
            val info = packageManager.getApplicationInfo(sbn.packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (_: Exception) {
            sbn.packageName
        }

        val payload = PayloadExtraction.fromExtras(
            extras = sbn.notification.extras,
            appName = appName,
            flags = sbn.notification.flags,
        ) ?: return

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
                Result.ErrorKind.Unauthorized -> {
                    settings.clear()
                    sendBroadcast(Intent(ACTION_LOGOUT))
                }
                Result.ErrorKind.BadRequest, Result.ErrorKind.NotFound -> {
                    settings.recordError()
                    broadcastStats()
                }
            }
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

    companion object {
        const val ACTION_STATS = "io.skillwood.client.STATS"
        const val ACTION_LOGOUT = "io.skillwood.client.LOGOUT"
    }
}
