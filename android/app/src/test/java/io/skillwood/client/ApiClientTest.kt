package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ApiClientTest {

    private lateinit var server: MockWebServer
    private lateinit var settings: SettingsRepository
    private lateinit var client: ApiClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        settings = SettingsRepository(ApplicationProvider.getApplicationContext())
        settings.clear()
        settings.serverUrl = server.url("/").toString().trimEnd('/')
        client = ApiClient(settings)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun ping_success() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok": true}"""))
        val r = client.ping(settings.serverUrl!!)
        assertTrue(r is Result.Success)
    }

    @Test
    fun connect_success_returns_token() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"token":"abc","user":{"id":1,"name":"Defi"},"device":{"id":1,"name":"Pad"}}"""
        ))
        val r = client.connect(settings.serverUrl!!, "12345678", "Pad")
        assertTrue(r is Result.Success)
        val data = (r as Result.Success).value
        assertEquals("abc", data.token)
        assertEquals("Defi", data.userName)
    }

    @Test
    fun connect_unknown_code_returns_not_found() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":"unknown code"}"""))
        val r = client.connect(settings.serverUrl!!, "00000000", "Pad")
        assertTrue(r is Result.Error)
        assertEquals(Result.ErrorKind.NotFound, (r as Result.Error).kind)
    }

    @Test
    fun send_notification_with_token_sends_bearer_header() = runBlocking {
        settings.deviceToken = "MY-TOKEN"
        server.enqueue(MockResponse().setResponseCode(200).setBody("OK"))
        val r = client.sendNotification("Иван", "привет", "Telegram")
        assertTrue(r is Result.Success)
        val req = server.takeRequest()
        assertEquals("Bearer MY-TOKEN", req.getHeader("Authorization"))
        val body = req.body.readUtf8()
        assertTrue(body.contains("sender="))
        assertTrue(body.contains("messenger_name=Telegram"))
    }

    @Test
    fun send_notification_unauthorized_returns_unauthorized() = runBlocking {
        settings.deviceToken = "BAD"
        server.enqueue(MockResponse().setResponseCode(401))
        val r = client.sendNotification("a", "b", "c")
        assertTrue(r is Result.Error)
        assertEquals(Result.ErrorKind.Unauthorized, (r as Result.Error).kind)
    }
}
