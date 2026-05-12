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

    fun recordSuccess() {
        prefs.edit()
            .putLong(KEY_SENT, sent + 1)
            .putLong(KEY_LAST_SENT, System.currentTimeMillis())
            .putInt(KEY_ERRORS, 0)
            .apply()
    }

    fun recordError() {
        prefs.edit().putInt(KEY_ERRORS, errorsStreak + 1).apply()
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
    }
}
