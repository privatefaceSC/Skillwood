package io.skillwood.client

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

data class ConnectResponse(
    val token: String,
    val userName: String,
    val deviceId: Long,
    val deviceName: String,
)

data class MeResponse(val userName: String, val deviceName: String)

class ApiClient(private val settings: SettingsRepository) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .build()

    suspend fun ping(serverUrl: String): Result<Unit> = withContext(Dispatchers.IO) {
        execute(Request.Builder().url("$serverUrl/api/ping").get().build()) { _ ->
            Result.Success(Unit)
        }
    }

    suspend fun connect(serverUrl: String, code: String, deviceName: String): Result<ConnectResponse> =
        withContext(Dispatchers.IO) {
            val body = JSONObject(mapOf("code" to code, "device_name" to deviceName))
                .toString()
                .toRequestBody("application/json".toMediaType())
            execute(
                Request.Builder().url("$serverUrl/api/connect").post(body).build()
            ) { responseBody ->
                val json = JSONObject(responseBody)
                Result.Success(
                    ConnectResponse(
                        token = json.getString("token"),
                        userName = json.getJSONObject("user").getString("name"),
                        deviceId = json.getJSONObject("device").getLong("id"),
                        deviceName = json.getJSONObject("device").getString("name"),
                    )
                )
            }
        }

    suspend fun me(): Result<MeResponse> = withContext(Dispatchers.IO) {
        val url = settings.serverUrl ?: return@withContext err(Result.ErrorKind.Unknown, "no url")
        val token = settings.deviceToken ?: return@withContext err(Result.ErrorKind.Unauthorized, "no token")
        execute(
            Request.Builder().url("$url/api/me")
                .header("Authorization", "Bearer $token").get().build()
        ) { body ->
            val json = JSONObject(body)
            Result.Success(MeResponse(
                userName = json.getJSONObject("user").getString("name"),
                deviceName = json.getJSONObject("device").getString("name"),
            ))
        }
    }

    suspend fun sendNotification(sender: String, text: String, messenger: String): Result<Unit> =
        withContext(Dispatchers.IO) {
            val url = settings.serverUrl ?: return@withContext err(Result.ErrorKind.Unknown, "no url")
            val token = settings.deviceToken ?: return@withContext err(Result.ErrorKind.Unauthorized, "no token")
            val form = FormBody.Builder()
                .add("sender", sender).add("text", text)
                .add("messenger_name", messenger).build()
            execute(
                Request.Builder().url("$url/add")
                    .header("Authorization", "Bearer $token").post(form).build()
            ) { _ ->
                Result.Success(Unit)
            }
        }

    suspend fun sendMedia(
        sender: String,
        messenger: String,
        kind: String,
        dedupKey: String,
        bytes: ByteArray,
        mime: String?,
    ): Result<Unit> = withContext(Dispatchers.IO) {
        val url = settings.serverUrl ?: return@withContext err(Result.ErrorKind.Unknown, "no url")
        val token = settings.deviceToken
            ?: return@withContext err(Result.ErrorKind.Unauthorized, "no token")
        val fileType = (mime ?: "application/octet-stream").toMediaTypeOrNull()
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("sender", sender)
            .addFormDataPart("messenger_name", messenger)
            .addFormDataPart("kind", kind)
            .addFormDataPart("dedup_key", dedupKey)
            .addFormDataPart("file", "media", bytes.toRequestBody(fileType))
            .build()
        execute(
            Request.Builder().url("$url/add_media")
                .header("Authorization", "Bearer $token").post(body).build()
        ) { _ -> Result.Success(Unit) }
    }

    private inline fun <T> execute(
        request: Request,
        onSuccess: (String) -> Result<T>,
    ): Result<T> {
        return try {
            http.newCall(request).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                when (resp.code) {
                    in 200..299 -> onSuccess(body)
                    400 -> err(Result.ErrorKind.BadRequest, "bad request")
                    401 -> err(Result.ErrorKind.Unauthorized, "unauthorized")
                    404 -> err(Result.ErrorKind.NotFound, "not found")
                    in 500..599 -> err(Result.ErrorKind.Server, "server $resp")
                    else -> err(Result.ErrorKind.Unknown, "http ${resp.code}")
                }
            }
        } catch (e: IOException) {
            err(Result.ErrorKind.Network, e.message ?: "network")
        } catch (e: Exception) {
            err(Result.ErrorKind.Unknown, e.message ?: "unknown")
        }
    }

    private fun <T> err(kind: Result.ErrorKind, msg: String): Result<T> = Result.Error(msg, kind)
}
