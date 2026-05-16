package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class SettingsRepositoryTest {

    private lateinit var repo: SettingsRepository

    @Before
    fun setUp() {
        repo = SettingsRepository(ApplicationProvider.getApplicationContext())
        repo.clear()
    }

    @Test
    fun freshly_initialized_is_not_configured() {
        assertFalse(repo.isConfigured())
        assertNull(repo.deviceToken)
        assertNull(repo.serverUrl)
    }

    @Test
    fun stores_and_returns_credentials() {
        repo.serverUrl = "http://192.168.1.3:5000"
        repo.deviceToken = "tkn-xyz"
        repo.userName = "Defi"
        repo.deviceName = "Pad"
        assertTrue(repo.isConfigured())
        assertEquals("http://192.168.1.3:5000", repo.serverUrl)
        assertEquals("tkn-xyz", repo.deviceToken)
        assertEquals("Defi", repo.userName)
        assertEquals("Pad", repo.deviceName)
    }

    @Test
    fun record_success_increments_counter_and_resets_errors() {
        repo.recordError()
        repo.recordError()
        assertEquals(2, repo.errorsStreak)
        repo.recordSuccess()
        assertEquals(1, repo.sent)
        assertEquals(0, repo.errorsStreak)
    }

    @Test
    fun record_error_increments_errors_streak() {
        repo.recordError()
        repo.recordError()
        repo.recordError()
        assertEquals(3, repo.errorsStreak)
    }

    @Test
    fun clear_removes_token_and_resets_stats() {
        repo.deviceToken = "x"
        repo.recordSuccess()
        repo.recordError()
        repo.clear()
        assertNull(repo.deviceToken)
        assertEquals(0, repo.sent)
        assertEquals(0, repo.errorsStreak)
    }

    @Test
    fun allowed_packages_default_is_empty() {
        assertTrue(repo.allowedPackages.isEmpty())
        assertFalse(repo.isPackageAllowed("org.telegram.messenger"))
    }

    @Test
    fun set_package_allowed_adds_and_persists() {
        repo.setPackageAllowed("org.telegram.messenger", true)
        assertTrue(repo.isPackageAllowed("org.telegram.messenger"))
        assertEquals(setOf("org.telegram.messenger"), repo.allowedPackages)
    }

    @Test
    fun set_package_allowed_false_removes_from_set() {
        repo.setPackageAllowed("org.telegram.messenger", true)
        repo.setPackageAllowed("ru.oneme.app", true)
        repo.setPackageAllowed("org.telegram.messenger", false)
        assertFalse(repo.isPackageAllowed("org.telegram.messenger"))
        assertTrue(repo.isPackageAllowed("ru.oneme.app"))
        assertEquals(setOf("ru.oneme.app"), repo.allowedPackages)
    }

    @Test
    fun set_package_allowed_is_idempotent() {
        repo.setPackageAllowed("org.telegram.messenger", true)
        repo.setPackageAllowed("org.telegram.messenger", true)
        assertEquals(setOf("org.telegram.messenger"), repo.allowedPackages)
    }

    @Test
    fun clear_resets_allowed_packages() {
        repo.setPackageAllowed("org.telegram.messenger", true)
        repo.setPackageAllowed("ru.oneme.app", true)
        repo.clear()
        assertTrue(repo.allowedPackages.isEmpty())
    }

    @Test
    fun record_unauthorized_increments_streak_and_returns_new_value() {
        assertEquals(0, repo.unauthStreak)
        assertEquals(1, repo.recordUnauthorized())
        assertEquals(2, repo.recordUnauthorized())
        assertEquals(2, repo.unauthStreak)
    }

    @Test
    fun record_success_resets_unauth_streak() {
        repo.recordUnauthorized()
        repo.recordUnauthorized()
        repo.recordSuccess()
        assertEquals(0, repo.unauthStreak)
    }

    @Test
    fun clear_auth_wipes_token_but_keeps_url_whitelist_and_stats() {
        repo.serverUrl = "http://192.168.1.3:5000"
        repo.deviceToken = "tkn-xyz"
        repo.userName = "Defi"
        repo.deviceName = "Pad"
        repo.setPackageAllowed("org.telegram.messenger", true)
        repo.recordSuccess()
        repo.recordUnauthorized()
        repo.recordUnauthorized()

        repo.clearAuth()

        assertNull(repo.deviceToken)
        assertNull(repo.userName)
        assertNull(repo.deviceName)
        assertFalse(repo.isConfigured())
        assertEquals(0, repo.unauthStreak)
        // URL, whitelist и накопленная статистика сохраняются — переподключение не должно
        // заставлять пользователя настраивать клиента с нуля.
        assertEquals("http://192.168.1.3:5000", repo.serverUrl)
        assertEquals(setOf("org.telegram.messenger"), repo.allowedPackages)
        assertEquals(1, repo.sent)
    }

    @Test
    fun allowed_packages_returns_immutable_snapshot() {
        repo.setPackageAllowed("org.telegram.messenger", true)
        val snapshot = repo.allowedPackages
        // Если бы геттер вернул внутренний инстанс SharedPreferences-сета,
        // последующее присваивание могло бы вытащить новые данные через ту же ссылку.
        repo.setPackageAllowed("ru.oneme.app", true)
        assertEquals(setOf("org.telegram.messenger"), snapshot)
    }
}
