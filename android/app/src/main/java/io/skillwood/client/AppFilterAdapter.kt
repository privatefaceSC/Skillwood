package io.skillwood.client

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.widget.SwitchCompat
import androidx.recyclerview.widget.RecyclerView

class AppFilterAdapter(
    private val settings: SettingsRepository,
) : RecyclerView.Adapter<AppFilterAdapter.VH>() {

    private var allApps: List<AppInfo> = emptyList()
    private var visible: List<AppInfo> = emptyList()

    fun setApps(apps: List<AppInfo>) {
        allApps = apps
        visible = apps
        notifyDataSetChanged()
    }

    fun setQuery(query: String) {
        val needle = query.trim()
        visible = if (needle.isEmpty()) allApps
                  else allApps.filter { it.label.contains(needle, ignoreCase = true) }
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_app_filter, parent, false)
        return VH(v)
    }

    override fun getItemCount(): Int = visible.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        val app = visible[position]
        holder.label.text = app.label
        holder.icon.setImageDrawable(app.icon)

        // Снимаем listener перед изменением isChecked — иначе ресайклинг ViewHolder
        // триггерит «фантомные» onCheckedChange и портит SettingsRepository.
        holder.switch.setOnCheckedChangeListener(null)
        holder.switch.isChecked = settings.isPackageAllowed(app.packageName)
        holder.switch.setOnCheckedChangeListener { _, isChecked ->
            settings.setPackageAllowed(app.packageName, isChecked)
        }
        holder.itemView.setOnClickListener { holder.switch.toggle() }
    }

    class VH(view: View) : RecyclerView.ViewHolder(view) {
        val icon: ImageView = view.findViewById(R.id.app_icon)
        val label: TextView = view.findViewById(R.id.app_label)
        val switch: SwitchCompat = view.findViewById(R.id.app_switch)
    }
}
