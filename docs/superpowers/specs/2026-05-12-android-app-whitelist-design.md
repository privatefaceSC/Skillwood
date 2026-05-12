# Whitelist приложений в Android-клиенте

**Дата:** 2026-05-12
**Ветка:** feature/contacts
**Контекст:** Сейчас [SkillwoodListener.kt](../../../android/app/src/main/java/io/skillwood/client/SkillwoodListener.kt) фильтрует только своё приложение и шлёт на сервер уведомления от всего остального — включая системные, часы, GPay, Battery Saver и пр. Пользователю нужна явная кнопка «Выбрать приложения» в клиенте, где он сам отметит галочками те, от которых хочет получать уведомления.

## Решение в одном предложении

В `SettingsRepository` появляется множество `allowedPackages: Set<String>`. `SkillwoodListener` early-return'ит уведомление, если `sbn.packageName` не в этом множестве. Новый экран `AppFilterActivity` показывает все установленные launcher-приложения с галочками и поиском; пользователь открывает его кнопкой из active-блока главной активности.

## Семантика

**Whitelist, opt-in, default-empty.** После апдейта APK сразу никакие уведомления не пересылаются, пока пользователь не зайдёт в «Выбрать приложения» и не отметит хотя бы одно. Это сознательный выбор: один раз настроил — тихо работает только то, что ты выбрал.

Никакого auto-allow, никаких «системные / не системные» вкладок. Простая бинарная галочка на каждое приложение.

## Архитектура

Новые файлы (4 Kotlin + 2 layout):

1. **[AppFilterActivity.kt](../../../android/app/src/main/java/io/skillwood/client/AppFilterActivity.kt)** — `AppCompatActivity`. Заголовок «Выбрать приложения», EditText-поиск, RecyclerView. На onCreate грузит список приложений через `AppListLoader`, рендерит через `AppFilterAdapter`.
2. **[AppFilterAdapter.kt](../../../android/app/src/main/java/io/skillwood/client/AppFilterAdapter.kt)** — `RecyclerView.Adapter<ViewHolder>`. Хранит отображаемый список (после поиска), вью-холдер с иконкой + label + `MaterialSwitch`. На переключении свитча зовёт `SettingsRepository.setPackageAllowed`.
3. **[AppListLoader.kt](../../../android/app/src/main/java/io/skillwood/client/AppListLoader.kt)** — стейтлесс класс с одним методом `load(packageManager): List<AppInfo>`. Внутри: `pm.queryIntentActivities(MAIN+LAUNCHER intent)`, маппинг в `AppInfo(packageName, label, icon)`, исключение своего пакета, сортировка по label через локальный `Collator`. Вынесен отдельно ради тестируемости — Robolectric умеет иметь дело с фейковыми PackageManager'ами.
4. **[NotificationFilter.kt](../../../android/app/src/main/java/io/skillwood/client/NotificationFilter.kt)** — pure-function `shouldForward(packageName: String, ownPackage: String, allowed: Set<String>): Boolean`. Возвращает `packageName != ownPackage && packageName in allowed`. Вынесена, чтобы протестировать фильтрацию без мока листенера.
5. **[activity_app_filter.xml](../../../android/app/src/main/res/layout/activity_app_filter.xml)** — поиск-поле сверху + RecyclerView. `MaterialToolbar` с заголовком.
6. **[item_app_filter.xml](../../../android/app/src/main/res/layout/item_app_filter.xml)** — горизонтальный LinearLayout: ImageView (иконка 40dp) + TextView (label, flex) + MaterialSwitch.

Точечные правки в существующих файлах:

- **[SettingsRepository.kt](../../../android/app/src/main/java/io/skillwood/client/SettingsRepository.kt)** — новые проперти `allowedPackages`, методы `setPackageAllowed(pkg, allowed)`, `isPackageAllowed(pkg)`. `clear()` теперь стирает и эту ключ-пару (это уже работает через `prefs.edit().clear()`, отдельно прописывать не надо).
- **[SkillwoodListener.kt](../../../android/app/src/main/java/io/skillwood/client/SkillwoodListener.kt)** — на старте `onNotificationPosted` после проверки `isConfigured()`: `if (!NotificationFilter.shouldForward(sbn.packageName, applicationContext.packageName, settings.allowedPackages)) return`. Замена существующей проверки `sbn.packageName == applicationContext.packageName`.
- **[MainActivity.kt](../../../android/app/src/main/java/io/skillwood/client/MainActivity.kt)** — onClick listener на новой кнопке, открывает `AppFilterActivity` через `startActivity(Intent(this, AppFilterActivity::class.java))`.
- **[activity_main.xml](../../../android/app/src/main/res/layout/activity_main.xml)** — кнопка `@+id/btn_app_filter` в `active_block` между «Тест» и «Отключить».
- **[AndroidManifest.xml](../../../android/app/src/main/AndroidManifest.xml)** — `<queries>` с MAIN+LAUNCHER intent для package visibility на API 30+, и `<activity android:name=".AppFilterActivity" android:exported="false"/>`.
- **[strings.xml](../../../android/app/src/main/res/values/strings.xml)** — `action_app_filter`, `app_filter_title`, `app_filter_search_hint`, `app_filter_empty`.

## Ключевые детали

### Package visibility на Android 11+

Чтобы `pm.queryIntentActivities(MAIN+LAUNCHER intent)` возвращал реальный список, в манифест добавляется:

```xml
<queries>
    <intent>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
    </intent>
</queries>
```

Это даёт видимость приложений, у которых есть launcher-иконка — то есть всё, что пользователь видит в своём списке приложений. `QUERY_ALL_PACKAGES` (более широкое разрешение, требующее обоснования в Play Store) **не используем**. Skillwood распространяется через APK через свой же сервер, но всё равно лучше идти узкой queries-схемой.

### Сохранение Set<String>

```kotlin
var allowedPackages: Set<String>
    get() = prefs.getStringSet(KEY_ALLOWED_PACKAGES, emptySet())!!.toSet()
    set(value) { prefs.edit().putStringSet(KEY_ALLOWED_PACKAGES, value).apply() }

fun setPackageAllowed(packageName: String, allowed: Boolean) {
    val cur = allowedPackages.toMutableSet()
    if (allowed) cur.add(packageName) else cur.remove(packageName)
    allowedPackages = cur
}

fun isPackageAllowed(packageName: String): Boolean = packageName in allowedPackages
```

Геттер копирует через `toSet()`, чтобы вернуть immutable-снимок (SharedPreferences возвращает изменяемый внутренний инстанс, который потом нельзя модифицировать напрямую — это известная грабля).

### Listener: один новый guard

```kotlin
override fun onNotificationPosted(sbn: StatusBarNotification) {
    if (!settings.isConfigured()) return
    if (!NotificationFilter.shouldForward(
            sbn.packageName, applicationContext.packageName,
            settings.allowedPackages)) return
    // ... остальное как было
}
```

### Поиск в адаптере

```kotlin
fun setQuery(q: String) {
    val needle = q.trim()
    visible = if (needle.isEmpty()) allApps
              else allApps.filter { it.label.contains(needle, ignoreCase = true) }
    notifyDataSetChanged()
}
```

`notifyDataSetChanged` — а не diffutil. Список меняется только когда пользователь печатает в поиске, и его пара сотен айтемов; diff-machinery тут перебор.

### Состояние свитчей при перерендере

`AppFilterAdapter` хранит ссылку на `SettingsRepository`. При биндинге каждого свитча: `holder.switch.isChecked = settings.isPackageAllowed(item.packageName)`. На onChange: вызываем `settings.setPackageAllowed(item.packageName, isChecked)`. Никаких ListenerSelf-ссылок, никакого `notifyItemChanged` после клика — RecyclerView переиспользует ViewHolder с актуальным состоянием при следующем bind.

**Грабля:** при ресайклинге ViewHolder может вызваться onChange предыдущего свитча в момент `isChecked = ...`. Стандартный фикс: перед `setChecked` снять listener, поставить значение, поставить listener обратно.

### Иконка приложения

`pm.getApplicationIcon(packageName)` возвращает `Drawable`. Кэшировать в адаптере не нужно — Android сам это делает на уровне ресурсов; иконки занимают копейки.

## Тесты

### `NotificationFilterTest.kt` (JUnit, без Robolectric)

```kotlin
@Test fun own_package_is_rejected_even_if_allowed()
@Test fun unknown_package_is_rejected()
@Test fun allowed_package_passes()
@Test fun empty_allowed_set_rejects_everything()
```

### `SettingsRepositoryTest.kt` (доп. кейсы в существующий файл, Robolectric)

```kotlin
@Test fun allowed_packages_default_is_empty()
@Test fun set_package_allowed_adds_to_set()
@Test fun set_package_allowed_false_removes_from_set()
@Test fun set_package_allowed_is_idempotent()
@Test fun clear_resets_allowed_packages()
```

### `AppListLoaderTest.kt` (Robolectric)

```kotlin
@Test fun returns_launcher_apps_sorted_by_label()
@Test fun excludes_own_package()
@Test fun empty_when_no_launcher_apps()
```

Реализуется через Robolectric'овский `ShadowPackageManager` — там есть `addPackage(...)` и `addIntentFilterForActivity(...)`.

### `AppFilterActivityTest.kt` (Robolectric, опционально)

Один смоук-тест: запускаем activity, проверяем, что в RecyclerView есть N айтемов, что переключение свитча обновляет `SettingsRepository`. Если время поджимает — можно отложить, потому что логика уже покрыта Adapter-агностичными тестами выше.

## Что НЕ делаем

- Не делаем auto-allow «похожих на мессенджер» (вариант (в) из обсуждения).
- Не разделяем системные и пользовательские — просто фильтруем по наличию launcher-иконки.
- Не блокируем уведомления per-conversation, только per-app.
- Не синхронизируем список с сервером — это локальная настройка устройства.
- Не делаем bulk «Включить всё / Выключить всё» (если понадобится — добавим позже двумя строчками в Activity).
- Не показываем баннер «Включите приложения» в `MainActivity`, если `allowedPackages.isEmpty()`. Сейчас обходимся без — кнопка достаточно очевидна. Если в проде окажется неочевидно, накатим follow-up.
- Не фильтруем `OutgoingQueue`. То, что уже в очереди из старой жизни, уйдёт — это короткий хвост.

## Файлы

Новые:
- `android/app/src/main/java/io/skillwood/client/NotificationFilter.kt`
- `android/app/src/main/java/io/skillwood/client/AppFilterActivity.kt`
- `android/app/src/main/java/io/skillwood/client/AppFilterAdapter.kt`
- `android/app/src/main/java/io/skillwood/client/AppListLoader.kt`
- `android/app/src/main/res/layout/activity_app_filter.xml`
- `android/app/src/main/res/layout/item_app_filter.xml`
- `android/app/src/test/java/io/skillwood/client/NotificationFilterTest.kt`
- `android/app/src/test/java/io/skillwood/client/AppListLoaderTest.kt`

Изменения:
- `android/app/src/main/java/io/skillwood/client/SettingsRepository.kt`
- `android/app/src/main/java/io/skillwood/client/SkillwoodListener.kt`
- `android/app/src/main/java/io/skillwood/client/MainActivity.kt`
- `android/app/src/main/res/layout/activity_main.xml`
- `android/app/src/main/res/values/strings.xml`
- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/test/java/io/skillwood/client/SettingsRepositoryTest.kt`
