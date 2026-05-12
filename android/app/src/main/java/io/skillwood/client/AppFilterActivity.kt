package io.skillwood.client

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AppFilterActivity : AppCompatActivity() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private lateinit var settings: SettingsRepository
    private lateinit var adapter: AppFilterAdapter
    private lateinit var emptyView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            setContentView(R.layout.activity_app_filter)

            settings = SettingsRepository(this)
            adapter = AppFilterAdapter(settings)

            val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
            setSupportActionBar(toolbar)
            supportActionBar?.setDisplayHomeAsUpEnabled(true)

            val recycler = findViewById<RecyclerView>(R.id.recycler)
            recycler.layoutManager = LinearLayoutManager(this)
            recycler.adapter = adapter
            emptyView = findViewById(R.id.empty_view)

            val search = findViewById<TextInputEditText>(R.id.input_search)
            search.addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    adapter.setQuery(s?.toString().orEmpty())
                    renderEmpty()
                }
            })

            loadApps()
        } catch (t: Throwable) {
            Log.e("AppFilterActivity", "onCreate failed", t)
            throw t
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.coroutineContext[Job]?.cancel()
    }

    private fun loadApps() {
        val ownPackage = applicationContext.packageName
        scope.launch {
            val apps = try {
                withContext(Dispatchers.IO) {
                    AppListLoader(ownPackage).load(packageManager)
                }
            } catch (t: Throwable) {
                Log.e("AppFilterActivity", "AppListLoader failed", t)
                emptyList()
            }
            adapter.setApps(apps)
            renderEmpty()
        }
    }

    private fun renderEmpty() {
        emptyView.visibility = if (adapter.itemCount == 0) View.VISIBLE else View.GONE
    }
}
