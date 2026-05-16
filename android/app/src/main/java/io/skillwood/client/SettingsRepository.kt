package io.skillwood.client

import android.content.Context
import android.content.SharedPreferences

class SettingsRepository(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var serverUrl: String?
        get() = prefs.getString(KEY_URL, null)
        set(value) { prefs.edit().putString(KEY_URL, value).apply() }

    var deviceToken: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) { prefs.edit().putString(KEY_TOKEN, value).apply() }

    var userName: String?
        get() = prefs.getString(KEY_USER_NAME, null)
        set(value) { prefs.edit().putString(KEY_USER_NAME, value).apply() }

    var deviceName: String?
        get() = prefs.getString(KEY_DEVICE_NAME, null)
        set(value) { prefs.edit().putString(KEY_DEVICE_NAME, value).apply() }

    val sent: Long
        get() = prefs.getLong(KEY_SENT, 0)

    val errorsStreak: Int
        get() = prefs.getInt(KEY_ERRORS, 0)

    val unauthStreak: Int
        get() = prefs.getInt(KEY_UNAUTH_STREAK, 0)

    val lastSentAt: Long
        get() = prefs.getLong(KEY_LAST_SENT, 0)

    fun isConfigured(): Boolean = !deviceToken.isNullOrBlank()

    /** Whitelist пакетов, от которых пересылаем уведомления. Пустой по умолчанию. */
    var allowedPackages: Set<String>
        get() = prefs.getStringSet(KEY_ALLOWED_PACKAGES, emptySet())!!.toSet()
        set(value) { prefs.edit().putStringSet(KEY_ALLOWED_PACKAGES, value).apply() }

    fun setPackageAllowed(packageName: String, allowed: Boolean) {
        val cur = allowedPackages.toMutableSet()
        if (allowed) cur.add(packageName) else cur.remove(packageName)
        allowedPackages = cur
    }

    fun isPackageAllowed(packageName: String): Boolean = packageName in allowedPackages

    /** Уже отправляли это медиа? Защита от повторных накопительных уведомлений. */
    fun wasMediaSent(key: String): Boolean =
        prefs.getStringSet(KEY_SENT_MEDIA, emptySet())!!.contains(key)

    fun markMediaSent(key: String) {
        val cur = HashSet(prefs.getStringSet(KEY_SENT_MEDIA, emptySet())!!)
        // Дедуп нужен только против повторов в близких по времени уведомлениях,
        // полная история не требуется — при переполнении просто сбрасываем.
        if (cur.size >= 500) cur.clear()
        cur.add(key)
        prefs.edit().putStringSet(KEY_SENT_MEDIA, cur).apply()
    }

    fun recordSuccess() {
        prefs.edit()
            .putLong(KEY_SENT, sent + 1)
            .putLong(KEY_LAST_SENT, System.currentTimeMillis())
            .putInt(KEY_ERRORS, 0)
            .putInt(KEY_UNAUTH_STREAK, 0)
            .apply()
    }

    fun recordError() {
        prefs.edit().putInt(KEY_ERRORS, errorsStreak + 1).apply()
    }

    /** Инкрементит счётчик подряд идущих 401 и возвращает новое значение. */
    fun recordUnauthorized(): Int {
        val next = unauthStreak + 1
        prefs.edit().putInt(KEY_UNAUTH_STREAK, next).apply()
        return next
    }

    /**
     * Стирает только то, что относится к аккаунту (токен, имя пользователя/устройства,
     * счётчик 401). Сохраняет URL сервера, whitelist пакетов и накопленную статистику —
     * пользователю не придётся настраивать клиента с нуля после повторного re-connect.
     */
    fun clearAuth() {
        prefs.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_USER_NAME)
            .remove(KEY_DEVICE_NAME)
            .putInt(KEY_UNAUTH_STREAK, 0)
            .apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val PREFS = "skillwood"
        private const val KEY_URL = "server_url"
        private const val KEY_TOKEN = "device_token"
        private const val KEY_USER_NAME = "user_name"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_SENT = "stats_sent"
        private const val KEY_LAST_SENT = "stats_last_sent_at"
        private const val KEY_ERRORS = "stats_errors_streak"
        private const val KEY_ALLOWED_PACKAGES = "allowed_packages"
        private const val KEY_UNAUTH_STREAK = "auth_unauth_streak"
        private const val KEY_SENT_MEDIA = "sent_media_keys"
    }
}
