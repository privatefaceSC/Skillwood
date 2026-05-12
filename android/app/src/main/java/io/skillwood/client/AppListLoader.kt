package io.skillwood.client

import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import java.text.Collator
import java.util.Locale

data class AppInfo(
    val packageName: String,
    val label: String,
    val icon: Drawable?,
)

/** Собирает список пользовательских приложений (с MAIN/LAUNCHER intent),
 *  исключает своё приложение, сортирует по label локалью устройства. */
class AppListLoader(private val ownPackage: String) {

    fun load(pm: PackageManager): List<AppInfo> {
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val resolveInfos = pm.queryIntentActivities(intent, 0)
        val seen = HashSet<String>()
        val result = ArrayList<AppInfo>(resolveInfos.size)
        for (ri in resolveInfos) {
            val pkg = ri.activityInfo.packageName ?: continue
            if (pkg == ownPackage) continue
            if (!seen.add(pkg)) continue
            val label = try {
                ri.loadLabel(pm)?.toString() ?: pkg
            } catch (_: Exception) {
                pkg
            }
            val icon = try {
                ri.loadIcon(pm)
            } catch (_: Exception) {
                null
            }
            result.add(AppInfo(pkg, label, icon))
        }
        val collator = Collator.getInstance(Locale.getDefault())
        result.sortWith(Comparator { a, b -> collator.compare(a.label, b.label) })
        return result
    }
}
