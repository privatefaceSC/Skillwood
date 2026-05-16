package io.skillwood.client

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
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
    private lateinit var btnFilesAccess: MaterialButton
    private lateinit var btnOverlayAccess: MaterialButton
    private lateinit var btnFsiAccess: MaterialButton

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
        findViewById<MaterialButton>(R.id.btn_app_filter).setOnClickListener {
            startActivity(Intent(this, AppFilterActivity::class.java))
        }
        findViewById<MaterialButton>(R.id.btn_check_access).setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        btnFilesAccess = findViewById(R.id.btn_files_access)
        btnFilesAccess.setOnClickListener { openAllFilesAccess() }
        btnOverlayAccess = findViewById(R.id.btn_overlay_access)
        btnOverlayAccess.setOnClickListener { openOverlayAccess() }
        btnFsiAccess = findViewById(R.id.btn_fsi_access)
        btnFsiAccess.setOnClickListener { openFullScreenIntentAccess() }
        findViewById<MaterialButton>(R.id.btn_miui_bg).setOnClickListener { openMiuiPermissions() }
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
        btnFilesAccess.text = getString(
            if (hasAllFilesAccess()) R.string.action_files_access_granted
            else R.string.action_files_access
        )
        btnOverlayAccess.text = getString(
            if (Settings.canDrawOverlays(this)) R.string.action_overlay_access_granted
            else R.string.action_overlay_access
        )
        btnFsiAccess.text = getString(
            if (canUseFullScreenIntent()) R.string.action_fsi_access_granted
            else R.string.action_fsi_access
        )
    }

    /** На Android 14+ USE_FULL_SCREEN_INTENT не автогрантится — нужен явный
     *  грант пользователем. До 14 — обычное разрешение, считается выданным. */
    private fun canUseFullScreenIntent(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
        return getSystemService(NotificationManager::class.java).canUseFullScreenIntent()
    }

    private fun openFullScreenIntentAccess() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // До Android 14 отдельного экрана нет — открываем настройки уведомлений.
            startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
            return
        }
        try {
            startActivity(Intent(
                "android.settings.MANAGE_APP_USE_FULL_SCREEN_INTENT",
                Uri.parse("package:$packageName"),
            ))
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }
    }

    private fun openOverlayAccess() {
        try {
            startActivity(Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:$packageName"),
            ))
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION))
        }
    }

    /**
     * Открывает экран разрешений приложения в MIUI Security Center, где лежит
     * «Отображать всплывающие окна в фоновом режиме» (MIUI-проприетарное, в
     * стандартных настройках Android его нет). Сам тумблер выставить нельзя —
     * только открыть нужный экран. Fallback — обычные детали приложения.
     */
    private fun openMiuiPermissions() {
        val attempts = listOf(
            Intent("miui.intent.action.APP_PERM_EDITOR").apply {
                setClassName("com.miui.securitycenter",
                    "com.miui.permcenter.permissions.PermissionsEditorActivity")
                putExtra("extra_pkgname", packageName)
            },
            Intent("miui.intent.action.APP_PERM_EDITOR").apply {
                setClassName("com.miui.securitycenter",
                    "com.miui.permcenter.permissions.AppPermissionsEditorActivity")
                putExtra("extra_pkgname", packageName)
            },
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:$packageName")),
        )
        for (i in attempts) {
            try { startActivity(i); return } catch (_: Exception) { /* пробуем следующий */ }
        }
    }

    private fun hasAllFilesAccess(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
            Environment.isExternalStorageManager()

    private fun openAllFilesAccess() {
        // Всегда открываем системный экран (как кнопка «Доступ к уведомлениям»),
        // чтобы можно было и выдать, и отозвать/перепроверить вручную.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        try {
            startActivity(Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName"),
            ))
        } catch (_: Exception) {
            startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
        }
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
