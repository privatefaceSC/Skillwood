package io.skillwood.client

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

class QueueDrainWorker(ctx: Context, params: WorkerParameters)
    : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val settings = SettingsRepository(applicationContext)
        if (!settings.isConfigured()) return Result.success()
        val queue = OutgoingQueue(applicationContext)
        val pending = queue.peekAll()
        if (pending.isEmpty()) return Result.success()

        val client = ApiClient(settings)
        val sent = mutableListOf<Payload>()
        for (p in pending) {
            val r = client.sendNotification(p.sender, p.text, p.messengerName)
            if (r is io.skillwood.client.Result.Success) {
                sent.add(p); settings.recordSuccess()
            } else {
                break
            }
        }
        if (sent.isNotEmpty()) queue.remove(sent)
        return Result.success()
    }
}
