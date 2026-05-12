package io.skillwood.client

import android.content.ComponentName
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class AppListLoaderTest {

    private val pm: PackageManager =
        ApplicationProvider.getApplicationContext<android.content.Context>().packageManager

    private fun registerLauncherApp(pkg: String, label: String) {
        val shadow = shadowOf(pm)
        val info = android.content.pm.ApplicationInfo().apply {
            packageName = pkg
            this.name = label
        }
        val pkgInfo = android.content.pm.PackageInfo().apply {
            packageName = pkg
            applicationInfo = info
        }
        shadow.installPackage(pkgInfo)

        val activityName = "$pkg.MainActivity"
        val activityInfo = ActivityInfo().apply {
            packageName = pkg
            this.name = activityName
            applicationInfo = info
            nonLocalizedLabel = label
        }
        val ri = ResolveInfo().apply {
            this.activityInfo = activityInfo
            nonLocalizedLabel = label
        }
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
            component = ComponentName(pkg, activityName)
        }
        shadow.addResolveInfoForIntent(intent, ri)
        // Также для общего MAIN+LAUNCHER intent без component
        val anyIntent = Intent(Intent.ACTION_MAIN).apply { addCategory(Intent.CATEGORY_LAUNCHER) }
        shadow.addResolveInfoForIntent(anyIntent, ri)
    }

    @Test
    fun returns_launcher_apps_sorted_by_label() {
        registerLauncherApp("ru.oneme.app", "Max")
        registerLauncherApp("org.telegram.messenger", "Telegram")
        registerLauncherApp("com.whatsapp", "WhatsApp")

        val apps = AppListLoader(ownPackage = "io.skillwood.client").load(pm)
        val labels = apps.map { it.label }
        // По локали должно быть отсортировано: Max, Telegram, WhatsApp
        assertEquals(listOf("Max", "Telegram", "WhatsApp"), labels)
    }

    @Test
    fun excludes_own_package() {
        registerLauncherApp("io.skillwood.client", "Skillwood")
        registerLauncherApp("org.telegram.messenger", "Telegram")

        val apps = AppListLoader(ownPackage = "io.skillwood.client").load(pm)
        val packages = apps.map { it.packageName }
        assertFalse("io.skillwood.client" in packages)
        assertTrue("org.telegram.messenger" in packages)
    }

    @Test
    fun returns_empty_when_no_launcher_apps() {
        val apps = AppListLoader(ownPackage = "io.skillwood.client").load(pm)
        assertTrue(apps.isEmpty())
    }
}
