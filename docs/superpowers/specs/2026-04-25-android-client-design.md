# Android-клиент Skillwood

**Дата:** 2026-04-25
**Статус:** утверждено

## Контекст

Сейчас уведомления попадают в Skillwood через стороннее приложение MacroDroid: триггер «Получено уведомление» → действие «HTTP POST». Эта схема имеет три проблемы:

1. **Триггер `NotificationListenerService` в MacroDroid периодически перестаёт срабатывать** — особенно после рестартов системы или в фоне на Android-производителях с агрессивной экономией батареи (Xiaomi, Samsung). Пользователь не понимает, что произошло, и почему сообщения не доходят.
2. **Пользователь сам конфигурирует подстановку переменных** в HTTP-теле (`sender={not_title}&text={notification}&...`). При этом легко ошибиться: переменная неправильно названа → сервер получает буквальную строку `{not_title}`.
3. **MacroDroid — комбайн на сотни функций**, и для одной задачи «слушать уведомления → POST» он избыточно сложен.

Цель: **собственное узкоцелевое Android-приложение**, которое каждый пользователь Skillwood ставит на свой планшет/телефон. Одна задача, никаких триггеров и переменных, минимум настроек.

Аутентификация через **device-token**, чтобы один сервер мог работать с пользователями из разных сетей и за NAT-ом (где `request.remote_addr` совпадает у всех).

## Глоссарий

| Термин | Что значит |
|---|---|
| **Skillwood-сервер** | существующее Flask-приложение, которое уже принимает `POST /add` |
| **Клиент** | новое Android-приложение, которое мы делаем |
| **Device** | конкретный экземпляр клиента, привязанный к одному пользователю |
| **device-token** | случайная 32-байтовая строка, которой клиент аутентифицируется на сервере |
| **`connect_code`** | существующий 8-значный код, который пользователь видит на сайте после регистрации |

## Допущения

1. **Один пользователь — много устройств.** Один Skillwood-аккаунт может иметь несколько привязанных Device, у каждого свой токен. Это упрощает «второй планшет» и «замена телефона».
2. **Привязка по IP уходит** для Bearer-аутентифицированных запросов. Старая привязка по `tablet_ip` остаётся работать как fallback — для совместимости с текущим MacroDroid.
3. **Токен хранится хешированным** (`sha256(token).hexdigest()`) с UNIQUE-индексом. Сервер при каждом `/add` считает sha256 от Bearer-токена и ищет в индексе.
4. **Стек клиента:** Kotlin + classic Views (XML) + AndroidX + OkHttp + Coroutines. Compose не используем.
5. **`minSdk = 26` (Android 8.0)**, `targetSdk = 34`. NotificationListenerService стабильно работает с 8.0; покрытие устройств ≥95%.
6. **Сборка debug-вариантом в первой версии** — без релизного keystore. Android разрешает sideload-установку debug-APK без проблем. Релизная подпись добавится отдельной задачей, если понадобится.
7. **Распространение через сам Skillwood-сервер** — публичная страница `/download` с прямой ссылкой на `skillwood.apk`. Никакого Google Play, никакого внешнего хостинга.
8. **Только русский UI**, без локализации. Соответствует остальному проекту.
9. **Один экран в приложении** с тремя состояниями: «не настроен», «нет Notification Access», «активно». Никаких настроек фильтров приложений в UI первой версии — фильтр по умолчанию (см. §«Поведение Listener»).

## Архитектура

### Высокоуровневая схема

```
                        Пользователь
                             │
                             │ 1. /register на сайте
                             │ 2. видит connect_code
                             │ 3. открывает /download
                             │ 4. ставит APK на планшет
                             │ 5. вводит URL + connect_code + имя устройства
                             ▼
┌───────────────────────────────────┐         ┌──────────────────────────────┐
│ Android-планшет                   │         │ Skillwood-сервер             │
│                                   │         │                              │
│ MainActivity ──► SettingsRepo     │         │  POST /api/connect           │
│      │                            │ ◄──────►│   создаёт Device, возвращает │
│      ▼                            │         │   token                      │
│ ApiClient (OkHttp)                │         │                              │
│      │                            │         │  POST /add  (Bearer token)   │
│      ▼                            │ ◄──────►│   sha256(token) → Device     │
│ SkillwoodListener                 │         │   record_message(user_id…)   │
│   (NotificationListenerService)   │         │                              │
│      │                            │         │  GET /api/me                 │
│      ├──► OutgoingQueue (буфер)   │ ◄──────►│   проверяет токен            │
│      │                            │         │                              │
│ ForegroundService                 │         │  GET /api/ping               │
│   (persistent notification)       │ ◄──────►│   smoke check                │
└───────────────────────────────────┘         │                              │
                                              │  GET /download               │
                                              │   страница «Скачать клиент»  │
                                              │  GET /download/skillwood.apk │
                                              │   отдаёт APK                 │
                                              └──────────────────────────────┘
```

### Структура репозитория

```
Skillwood/
├── main.py, data/, templates/, ...        ← Flask, как сейчас
├── android/                                ← новый подкаталог
│   ├── app/
│   │   ├── src/main/java/io/skillwood/client/
│   │   │   ├── MainActivity.kt
│   │   │   ├── SettingsRepository.kt
│   │   │   ├── ApiClient.kt
│   │   │   ├── SkillwoodListener.kt
│   │   │   ├── OutgoingQueue.kt
│   │   │   └── ForegroundService.kt
│   │   ├── src/main/res/layout/activity_main.xml
│   │   ├── src/main/res/values/strings.xml
│   │   ├── src/main/AndroidManifest.xml
│   │   └── build.gradle.kts
│   ├── build.gradle.kts
│   ├── settings.gradle.kts
│   ├── gradle.properties
│   ├── gradlew, gradlew.bat
│   └── gradle/wrapper/...
├── dist/skillwood.apk                     ← собранный APK (в .gitignore)
└── scripts/build_apk.sh                   ← одна команда: cd android && ./gradlew assembleDebug && cp …
```

## Изменения на сервере

### Модель `Device`

В новом файле `data/devices.py`:

```python
class Device(SqlAlchemyBase):
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)               # «Xiaomi Pad 6»
    token_hash = Column(String, nullable=False, unique=True, index=True)
    last_seen_ip = Column(String, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
```

Регистрируется в `data/__all_models.py`. Миграция: `metadata.create_all` создаёт новую таблицу, никаких ALTER на существующих не нужно.

### Новые маршруты в `main.py`

| Метод | Путь | Тело | Возвращает | Назначение |
|---|---|---|---|---|
| POST | `/api/connect` | `{"code": str, "device_name": str}` | `{"token": str, "user": {"id", "name"}, "device": {"id", "name"}}` | Регистрация устройства. Ищет `User.connect_code`; если нашёл — генерит токен, создаёт `Device`. Возвращает токен в открытом виде **один раз** — клиент его сохраняет. |
| GET | `/api/me` | — | `{"user": {"id", "name"}, "device": {"id", "name"}}` | Проверка токена. Header `Authorization: Bearer <token>`. 401 если токен невалиден. |
| GET | `/api/ping` | — | `{"ok": true, "service": "skillwood"}` | Уже есть. |
| POST | `/add` | form: `sender`, `text`, `messenger_name` | `"OK"`/`"Bad Request"` | **Меняется поведение:** если есть Bearer — ищем по `token_hash`; иначе fallback на текущий IP-режим. |
| GET | `/download` | — | HTML | Публичная страница «Скачать клиент» со скриншотами-инструкциями и ссылкой на APK. |
| GET | `/download/skillwood.apk` | — | APK | `send_from_directory('dist', 'skillwood.apk')`. 404 если файла нет. |

### Изменение `POST /add`

Псевдокод:

```
POST /add (sender, text, messenger_name)
  if не все три поля → 400

  auth_header = request.headers.get('Authorization')
  if auth_header.startswith('Bearer '):
      token = auth_header[7:]
      device = db.query(Device).filter(token_hash == sha256(token)).first()
      if not device → 401
      device.last_seen_ip = remote_addr
      device.last_seen_at = now()
      user_id = device.user_id
  else:
      user = db.query(User).filter(tablet_ip == remote_addr).first()
      if not user → 200 + log "Неизвестное устройство"
      user_id = user.id

  record_message(db, user_id, messenger_name, sender, text)
  return 200 OK
```

### Главная и `/code`

На `/home` и `/code` добавить заметную карточку «Скачать Android-клиент» с кнопкой → `/download`.

## Android-приложение

### MainActivity — единственный экран, три состояния

#### Состояние 1: «Не настроен» (нет токена в SharedPreferences)

Поля:
- **Адрес сервера** — `EditText`, изначально пустой (пользователь вводит вручную). Если был сохранён предыдущий URL — подставляется как подсказка.
- **Код подключения** — `EditText` с фильтром на 8 цифр.
- **Имя устройства** — `EditText`, по умолчанию заполнен `${Build.MANUFACTURER} ${Build.MODEL}`, пользователь может поменять.

Кнопка **«Подключить»**:
1. Вызывает `ApiClient.connect(serverUrl, code, deviceName)`.
2. На успех — сохраняет `(serverUrl, token, userName, deviceName)` в `SettingsRepository`, переходит в состояние 2 или 3.
3. На ошибку — показывает текст ошибки красным под кнопкой.

#### Состояние 2: «Нет Notification Access»

Текст: «Чтобы Skillwood мог пересылать уведомления, дай ему доступ в системных настройках».
Кнопка **«Дать доступ»** → открывает `Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`.
Когда `Activity.onResume` обнаруживает, что доступ дан — переключается в состояние 3.

#### Состояние 3: «Активно»

Зелёная плашка статуса: «Skillwood работает • аккаунт {userName}».

Под ней блок статистики:
- Отправлено уведомлений: N
- Последнее: HH:MM (или «—»)
- Ошибок подряд: N (или «—»)
- В очереди ожидает: N (если есть pending)

Кнопки:
- **«Отправить тест»** — синтезирует уведомление с `sender="Тест"`, `text="Привет от Skillwood-клиента"`, `messenger_name="Skillwood Test"` и шлёт через `ApiClient.sendNotification`. Удобно убедиться, что соединение работает.
- **«Отключить устройство»** — удаляет токен локально, ставит в очередь `DELETE /api/devices/<id>` (опционально на будущее), возвращает в состояние 1.

### `SettingsRepository`

Простая обёртка над `SharedPreferences("skillwood", MODE_PRIVATE)`. Ключи:

| Ключ | Тип | Назначение |
|---|---|---|
| `server_url` | String | базовый URL Skillwood-сервера |
| `device_token` | String? | Bearer-токен, выданный сервером |
| `user_name` | String? | имя пользователя (для UI) |
| `device_name` | String? | имя устройства, как введено пользователем |
| `stats_sent` | Long | счётчик успешных отправок |
| `stats_last_sent_at` | Long | timestamp последней успешной отправки |
| `stats_errors_streak` | Int | счётчик подряд идущих ошибок |

API:
```kotlin
class SettingsRepository(ctx: Context) {
    var serverUrl: String?
    var deviceToken: String?
    var userName: String?
    var deviceName: String?
    fun isConfigured(): Boolean = deviceToken != null
    fun recordSuccess()  // increments stats_sent, updates stats_last_sent_at, resets stats_errors_streak
    fun recordError()    // increments stats_errors_streak
    fun clear()          // удаляет токен, имя — возвращает в состояние 1
    val stats: Flow<Stats>  // для подписки UI
}
```

### `ApiClient`

Поверх OkHttp. Все методы — `suspend`, возвращают `Result<T>` (sealed `Success(value)` / `Error(message, kind)`).

```kotlin
class ApiClient(private val settings: SettingsRepository) {
    suspend fun ping(serverUrl: String): Result<Unit>
    suspend fun connect(serverUrl: String, code: String, deviceName: String): Result<ConnectResponse>
    suspend fun me(): Result<MeResponse>
    suspend fun sendNotification(sender: String, text: String, messenger: String): Result<Unit>
}

data class ConnectResponse(val token: String, val userName: String, val deviceId: Long, val deviceName: String)
data class MeResponse(val userName: String, val deviceName: String)
```

`sendNotification` ставит заголовок `Authorization: Bearer ${settings.deviceToken}`. Тело — `application/x-www-form-urlencoded` (как и сейчас MacroDroid отправлял), три поля: `sender`, `text`, `messenger_name`.

Ошибки `Result.Error.kind`: `Network`, `Unauthorized`, `NotFound`, `BadRequest`, `Server`, `Unknown`.

### `SkillwoodListener` — главный сервис

```kotlin
class SkillwoodListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (shouldSkip(sbn)) return
        val payload = extractPayload(sbn) ?: return
        scope.launch { sendOrEnqueue(payload) }
    }
}
```

**`shouldSkip`** возвращает `true` если:
- `sbn.packageName == applicationContext.packageName` (наше собственное persistent-уведомление от ForegroundService).
- `sbn.notification.flags and FLAG_ONGOING_EVENT != 0` (играет музыка, идёт навигация).
- `sbn.notification.flags and FLAG_FOREGROUND_SERVICE != 0` (это служебка, не сообщение).

**`extractPayload(sbn)`**:
```kotlin
val pm = packageManager
val appName = pm.getApplicationLabel(pm.getApplicationInfo(sbn.packageName, 0)).toString()
val extras = sbn.notification.extras
val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
if (title.isBlank() || text.isBlank() || appName.isBlank()) return null
return Payload(sender = title, text = text, messengerName = appName)
```

**`sendOrEnqueue`**:
1. Пытается `ApiClient.sendNotification(...)`.
2. Успех → `settings.recordSuccess()`, бродкаст `STATS_UPDATED` для UI.
3. Ошибка типа `Network` или `Server` → `OutgoingQueue.add(payload)`, `settings.recordError()`.
4. Ошибка `Unauthorized` → `settings.clear()`, бродкаст `LOGOUT_REQUIRED` для UI.
5. Ошибка `BadRequest` → дроп без ретраев, ошибку логируем.

### `OutgoingQueue`

Локальный буфер на случай отсутствия сети. Реализован поверх SharedPreferences (одно поле `queue_json` со списком JSON-объектов). Лимит 200 элементов, FIFO-выброс старых.

```kotlin
class OutgoingQueue(ctx: Context) {
    fun add(p: Payload)               // добавляет, выбрасывает старые если >200
    fun peekAll(): List<Payload>      // для retry
    fun remove(items: List<Payload>)  // удаляет успешно отправленные
    fun size(): Int
}
```

**Retry workflow:** WorkManager periodic-задача каждые 30 секунд:
1. Если очередь пуста — выходит.
2. Берёт `peekAll()`, по одному шлёт через `ApiClient.sendNotification`.
3. Успешные — `remove(...)`. На первой Network-ошибке — прекращаем (вернётся через 30 сек).
4. Если перестаёт работать — `recordError()`.

### `ForegroundService`

Запускается из `MainActivity` после успешного «Подключения». Показывает persistent-уведомление «Skillwood работает • Listening for notifications». Это нужно, чтобы Android не убивал NotificationListener в фоне, как у MacroDroid.

При тапе по уведомлению — открывает `MainActivity`.

### AndroidManifest.xml — пермишны и сервисы

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"/>
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED"/>

<service android:name=".SkillwoodListener"
         android:exported="true"
         android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
    <intent-filter>
        <action android:name="android.service.notification.NotificationListenerService"/>
    </intent-filter>
</service>

<service android:name=".ForegroundService"
         android:foregroundServiceType="dataSync"
         android:exported="false"/>

<receiver android:name=".BootReceiver" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED"/>
    </intent-filter>
</receiver>
```

`BootReceiver` после ребута планшета поднимает ForegroundService, если в SharedPreferences есть валидный токен.

## Поведение в краевых ситуациях

| Ситуация | Поведение |
|---|---|
| Сервер не отвечает (timeout / no network) | Сообщение в очередь, retry через 30 сек / при следующем уведомлении / при появлении сети. UI показывает «Ошибок подряд: N». |
| HTTP 401 — токен инвалид | `settings.clear()`, persistent-уведомление пропадает, UI переходит в «Не настроен». Пользователь повторно вводит код. |
| HTTP 4xx (400 — невалидное тело) | Дроп сообщения с логом, не ретраим. |
| HTTP 5xx | Ретраим 3 раза с задержкой 1s/3s/9s. Если все три провалились — в очередь. |
| Notification Access отозван | `onListenerDisconnected()` — UI переключается в «Нет доступа», ForegroundService останавливается. |
| Очередь >200 элементов | FIFO: дропаем самые старые. Счётчик `stats_dropped` для статистики. |
| `extractPayload` вернул null (пустой title/text) | Молча пропускаем. Не считается ошибкой. |
| Boot complete | `BootReceiver` стартует ForegroundService если токен есть. NotificationListener Android поднимает сам. |

## Сборка и распространение

### Сборка

```bash
cd android
./gradlew assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk ../dist/skillwood.apk
```

Скрипт `scripts/build_apk.sh` делает то же одной командой. Это **не** запускается автоматически на каждый коммит — пользователь сам решает, когда обновить APK.

`dist/` в `.gitignore`. APK — артефакт, не source.

### Установка на планшет

Реальный пользователь:
1. Открывает в браузере планшета `http://<server>:5000/download`.
2. Тапает «Скачать APK». Браузер спрашивает «Установить из неизвестных источников?» → пользователь разрешает.
3. Открывает скачанный файл. Android ставит.
4. Открывает Skillwood-клиент. Вводит URL/код/имя. «Подключить».
5. Соглашается на Notification Access (системный экран).
6. Видит «Активно». Возвращается на сайт — сообщения идут.

### Обратная совместимость

Существующий MacroDroid продолжает работать через IP-режим в `POST /add`. Кто хочет — переходит на Android-клиент, кто не хочет — остаётся на MacroDroid. Спустя несколько недель IP-режим можно будет выпилить отдельной задачей.

## Тестирование

### На сервере (pytest)

| Тест | Что проверяет |
|---|---|
| `test_api_connect_creates_device` | `POST /api/connect` с правильным кодом → 200, в БД появился `Device`, `token_hash` непустой и уникальный. |
| `test_api_connect_rejects_wrong_code` | Неправильный `code` → 404. |
| `test_api_me_with_valid_token` | `GET /api/me` с валидным токеном → 200 + user.name. |
| `test_api_me_with_invalid_token` | Неправильный токен → 401. |
| `test_add_with_bearer_token_records_message` | `POST /add` с Bearer → создаёт сообщение, привязывает к `device.user_id`. |
| `test_add_with_invalid_bearer_token_returns_401` | Невалидный Bearer → 401. |
| `test_add_without_bearer_falls_back_to_ip` | Без Bearer работает как сейчас (IP-режим). |
| `test_download_apk_returns_file` | Если в `dist/` есть `skillwood.apk` → 200; если нет — 404. |
| `test_device_last_seen_updates` | `POST /add` обновляет `device.last_seen_ip` и `last_seen_at`. |

### На Android (JUnit + Robolectric для парсинга)

| Тест | Что проверяет |
|---|---|
| `OutgoingQueueTest.fifo_when_overflow` | При 201 элементе — старейший выбрасывается. |
| `OutgoingQueueTest.serialization_roundtrip` | После сериализации/десериализации содержимое идентично. |
| `ApiClientTest.connect_success` | Заглушка OkHttp 200 → `Result.Success` с токеном. |
| `ApiClientTest.connect_unknown_code` | Сервер ответил 404 на `/api/connect` → `Result.Error(NotFound)`. |
| `ApiClientTest.send_network_error` | Mock OkHttp `IOException` → `Result.Error(Network)`. |
| `PayloadExtractionTest.skips_when_title_blank` | Уведомление без title → null. |
| `PayloadExtractionTest.uses_big_text_when_present` | `EXTRA_BIG_TEXT` приоритетнее `EXTRA_TEXT`. |
| `PayloadExtractionTest.skips_ongoing_event` | `FLAG_ONGOING_EVENT` → пропуск. |

Instrumentation-тесты на эмуляторе/устройстве — за рамками. Для учебного проекта избыточно.

## Что НЕ делаем

- **iOS-клиент.** Отдельный проект, отдельные технологии.
- **Google Play Store.** $25 + ревью + иконки/скриншоты — для учебного проекта избыточно.
- **UI выбора фильтра приложений.** В первой версии — фильтр по умолчанию (FLAG_ONGOING/FOREGROUND/собственный пакет). Если потом окажется нужно — добавим экран настроек.
- **Автообновление APK.** Пользователь сам скачивает новую версию с `/download`.
- **Шифрование локальной очереди.** SharedPreferences без шифрования — для учебного проекта норма.
- **Compose UI / Material 3.** Усложняет сборку, увеличивает APK на 2 МБ, не даёт выгоды для одного экрана.
- **Многоаккаунтный режим на одном устройстве.** Один `Device` = один токен.
- **Push от сервера к клиенту.** Клиент только отправляет, ничего не получает.
- **i18n.** Только русский UI.
- **Темы / тёмный режим.** Используем системный по умолчанию.
- **Релизный keystore и подпись.** В первой версии debug-APK достаточно. Релизная подпись — отдельной задачей при необходимости.
- **DELETE `/api/devices/<id>`** для отзыва токена с сервера. В UI клиента кнопка «Отключить» только локально стирает токен. Серверный отзыв — на потом.
- **`POST /api/connect` через QR-код вместо ввода кода руками.** Удобство, но не критично — добавится отдельно.
