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
}
