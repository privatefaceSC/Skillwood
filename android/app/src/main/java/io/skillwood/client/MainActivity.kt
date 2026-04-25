package io.skillwood.client

import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var settings: SettingsRepository
    private lateinit var queue: OutgoingQueue
    private lateinit var apiClient: ApiClient

    private lateinit var setupBlock: View
    private lateinit var noAccessBlock: View
    private lateinit var activeBlock: View

    private lateinit var inputServer: TextInputEditText
    private lateinit var inputCode: TextInputEditText
    private lateinit var inputDeviceName: TextInputEditText
    private lateinit var setupError: TextView

    private lateinit var activeAccount: TextView
    private lateinit var statSent: TextView
    private lateinit var statLast: TextView
    private lateinit var statErrors: TextView
    private lateinit var statQueue: TextView

    private val scope = CoroutineScope(Dispatchers.Main)
    private val dateFormat = SimpleDateFormat("HH:mm", Locale.getDefault())

    private val statsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) { renderStats() }
    }

    private val logoutReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            ForegroundService.stop(this@MainActivity)
            renderState()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = SettingsRepository(this)
        queue = OutgoingQueue(this)
        apiClient = ApiClient(settings)

        setupBlock = findViewById(R.id.setup_block)
        noAccessBlock = findViewById(R.id.no_access_block)
        activeBlock = findViewById(R.id.active_block)

        inputServer = findViewById(R.id.input_server)
        inputCode = findViewById(R.id.input_code)
        inputDeviceName = findViewById(R.id.input_device_name)
        setupError = findViewById(R.id.setup_error)

        activeAccount = findViewById(R.id.active_account)
        statSent = findViewById(R.id.stat_sent)
        statLast = findViewById(R.id.stat_last)
        statErrors = findViewById(R.id.stat_errors)
        statQueue = findViewById(R.id.stat_queue)

        inputServer.setText(settings.serverUrl.orEmpty())
        inputDeviceName.setText(settings.deviceName ?: "${Build.MANUFACTURER} ${Build.MODEL}")

        findViewById<MaterialButton>(R.id.btn_connect).setOnClickListener { onConnect() }
        findViewById<MaterialButton>(R.id.btn_grant_access).setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        findViewById<MaterialButton>(R.id.btn_test).setOnClickListener { onTest() }
        findViewById<MaterialButton>(R.id.btn_disconnect).setOnClickListener { onDisconnect() }
    }

    override fun onResume() {
        super.onResume()
        androidx.core.content.ContextCompat.registerReceiver(
            this, statsReceiver,
            IntentFilter(SkillwoodListener.ACTION_STATS),
            androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        androidx.core.content.ContextCompat.registerReceiver(
            this, logoutReceiver,
            IntentFilter(SkillwoodListener.ACTION_LOGOUT),
            androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        renderState()
    }

    override fun onPause() {
        super.onPause()
        unregisterReceiver(statsReceiver)
        unregisterReceiver(logoutReceiver)
    }

    private fun renderState() {
        when {
            !settings.isConfigured() -> showOnly(setupBlock)
            !isNotificationListenerEnabled() -> showOnly(noAccessBlock)
            else -> { showOnly(activeBlock); ForegroundService.start(this); renderStats() }
        }
    }

    private fun showOnly(block: View) {
        setupBlock.visibility = if (block === setupBlock) View.VISIBLE else View.GONE
        noAccessBlock.visibility = if (block === noAccessBlock) View.VISIBLE else View.GONE
        activeBlock.visibility = if (block === activeBlock) View.VISIBLE else View.GONE
    }

    private fun renderStats() {
        activeAccount.text = getString(R.string.state_active_account, settings.userName ?: "—")
        statSent.text = getString(R.string.stat_sent, settings.sent.toInt())
        statLast.text = getString(
            R.string.stat_last_sent,
            if (settings.lastSentAt > 0) dateFormat.format(Date(settings.lastSentAt)) else "—",
        )
        statErrors.text = getString(R.string.stat_errors, settings.errorsStreak)
        statQueue.text = getString(R.string.stat_queue, queue.size())
    }

    private fun isNotificationListenerEnabled(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: ""
        val cn = ComponentName(this, SkillwoodListener::class.java).flattenToString()
        return enabled.split(":").any { it == cn }
    }

    private fun onConnect() {
        val url = inputServer.text?.toString().orEmpty().trim().trimEnd('/')
        val code = inputCode.text?.toString().orEmpty().trim()
        val name = inputDeviceName.text?.toString().orEmpty().trim()
        if (url.isEmpty() || code.isEmpty() || name.isEmpty()) {
            setupError.text = "Заполните все поля"
            setupError.visibility = View.VISIBLE
            return
        }
        setupError.visibility = View.GONE
        scope.launch {
            val result = withContext(Dispatchers.IO) { apiClient.connect(url, code, name) }
            when (result) {
                is Result.Success -> {
                    settings.serverUrl = url
                    settings.deviceToken = result.value.token
                    settings.userName = result.value.userName
                    settings.deviceName = result.value.deviceName
                    renderState()
                }
                is Result.Error -> {
                    setupError.text = errorMessage(result.kind)
                    setupError.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun onTest() {
        scope.launch {
            withContext(Dispatchers.IO) {
                apiClient.sendNotification(
                    getString(R.string.test_sender),
                    getString(R.string.test_text),
                    getString(R.string.test_messenger),
                )
            }
            settings.recordSuccess()
            renderStats()
        }
    }

    private fun onDisconnect() {
        settings.clear()
        ForegroundService.stop(this)
        renderState()
    }

    private fun errorMessage(kind: Result.ErrorKind): String = when (kind) {
        Result.ErrorKind.Network -> getString(R.string.error_network)
        Result.ErrorKind.NotFound -> getString(R.string.error_unknown_code)
        Result.ErrorKind.Unauthorized -> getString(R.string.error_unauthorized)
        Result.ErrorKind.Server -> getString(R.string.error_server)
        else -> getString(R.string.error_unknown)
    }
}
