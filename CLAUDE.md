# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с этим репозиторием.

## Запуск приложения

```bash
# Активировать venv (Windows / bash)
source .venv/Scripts/activate

# Установка зависимостей
pip install -r requirements.txt

# Запустить Flask-сервер на 0.0.0.0:5000
python main.py
```

Зависимости зафиксированы в `requirements.txt` (Flask 3.1, Flask-Login, Flask-WTF, SQLAlchemy 2.0, sqlalchemy-serializer, Werkzeug, requests, pytest).

Тесты на `pytest` в [tests/](tests/). Запуск:

```bash
.venv/Scripts/pytest -v
```

Линтера и отдельного шага сборки в проекте нет.

## Архитектура

Это небольшое Flask-приложение, работающее как **мост между личным Android-устройством (с MacroDroid) и веб-панелью** для просмотра уведомлений из мессенджеров. Интерфейс и тексты — на русском.

### Создание приложения

Точка входа — `create_app(db_path="db/blogs.db")` в [main.py](main.py). Внутри: `db_sessions.global_init(db_path)`, создание Flask-app, регистрация маршрутов через `register_routes(app)`, `teardown_appcontext` для закрытия per-request сессии. Сессия создаётся лениво в `get_db()` и хранится в `flask.g.db`.

### Привязка устройства (центральная нетривиальная идея)

1. Регистрация на `/register` → сервер генерирует 8-значный `connect_code`, сохраняет на `User`.
2. Код показывается на `/code` (auto-refresh 3 секунды).
3. Android-устройство (макрос MacroDroid) делает `GET /connect?code=<код>`. Сервер сохраняет `request.remote_addr` как `User.tablet_ip`.
4. После заполнения `tablet_ip` страница `/code` редиректит на `/home`.
5. Уведомления из мессенджеров шлются через `POST /add` (поля `sender`, `text`, `messenger_name`). Пользователь определяется по совпадению `request.remote_addr` с `User.tablet_ip` — без токена. Стабильность IP в локалке критична.

### Контакт-центричная модель сообщений

Сообщения не валятся в одну ленту, а группируются по контактам:

```
User
 └─ 1:N → Contact(display_name)            ← реальный человек глазами владельца
            └─ 1:N → MessengerHandle       ← конкретная личность в конкретном мессенджере
                       └─ 1:N → Messages   ← сообщение, привязано к handle
```

`POST /add` ищет `MessengerHandle` по `(user_id, messenger_name, sender_raw)`. Не нашёл — создаёт новый `Contact` с `display_name = sender` и привязывает handle. После создания нового handle [data/matching.py](data/matching.py) сравнивает `sender_normalized` с другими handles того же `user_id`: при сходстве ≥ `MATCH_THRESHOLD = 0.7` создаётся `MergeSuggestion(status='pending')` для подсказки в UI.

UI:
- `/contacts` — двухпанельный лейаут (список / переписка).
- `/contacts/<id>` — переписка с контактом, агрегирует сообщения всех его handles.
- `/contacts/manage` — управление связями: переименование, перемещение handle между контактами, объединение контактов, принятие/скрытие подсказок.

Старый `/messages` редиректит на `/contacts`.

### Слой данных

- **SQLite** в `db/blogs.db`. Путь по умолчанию в `create_app("db/blogs.db")`, в тестах — `:memory:`.
- Engine создаётся с `check_same_thread=False`. Сессия — **per-request** через `flask.g`: `get_db()` создаёт сессию при первом обращении в обработчике, `teardown_appcontext` закрывает.
- Модели:
  - [data/users.py](data/users.py) — `User`, `Messages`. У `Messages` поля `handle_id` (FK) и `created_at` добавлены под контакты; `sender`/`messenger_name` остаются как исторический снимок.
  - [data/contacts.py](data/contacts.py) — `Contact`, `MessengerHandle`, `MergeSuggestion`, плюс сервисные функции `find_or_create_handle`, `record_message`, `merge_contacts`.
- [data/matching.py](data/matching.py) — `normalize`, `similarity_score`, `MATCH_THRESHOLD`, `suggest_merges_for_handle`. Использует `difflib` (stdlib), без новых зависимостей.
- Новые модели должны импортироваться в [data/__all_models.py](data/__all_models.py).
- `data/db_sessions.py` экспортирует `global_init`, `create_session`, `_reset_for_tests` (последняя — только для pytest-фикстур).

### Маршруты

Все живут в [main.py](main.py). Авторизация — через `flask.session['user_id']`; декоратора `@login_required` нет, каждый защищённый маршрут проверяет `session.get('user_id')` вручную.

- `/`, `/home`, `/login`, `/register`, `/logout`, `/code` — страницы аутентификации/профиля.
- `/connect` (GET) — привязка устройства, дёргается из MacroDroid.
- `/add` (POST) — приём сообщений, дёргается из MacroDroid; пользователь определяется по `remote_addr`. Возвращает 400 без обязательных полей, 200 без логирования если устройство не привязано к пользователю.
- `/contacts`, `/contacts/<id>`, `/contacts/manage` — UI.
- `/contacts/<id>/rename`, `/contacts/merge`, `/contacts/handles/<id>/move` — управление связями.
- `/contacts/suggestions/<id>/accept`, `.../dismiss` — действия по подсказкам.

### Миграция исторических данных

[data/migrations.py](data/migrations.py) `migrate_to_contacts_v1` — одноразовый скрипт (`python -m data.migrations`). Группирует существующие `Messages` по `(user_id, messenger_name, sender)` и создаёт под каждую группу `Contact + MessengerHandle`. Идемпотентна. Автомэтчинг для исторических данных намеренно не запускается — иначе UI завалится подсказками.

ВАЖНО: для существующей `db/blogs.db` нужно вручную добавить колонки `handle_id` и `created_at` в `messages` через `ALTER TABLE` перед запуском миграции — `SqlAlchemyBase.metadata.create_all` не делает ALTER на существующих таблицах. Команда:

```bash
.venv/Scripts/python -c "
import sqlite3
con = sqlite3.connect('db/blogs.db')
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(messages)').fetchall()]
if 'handle_id' not in cols:
    cur.execute('ALTER TABLE messages ADD COLUMN handle_id INTEGER REFERENCES messenger_handles(id)')
if 'created_at' not in cols:
    cur.execute('ALTER TABLE messages ADD COLUMN created_at DATETIME')
con.commit()
con.close()
"
```

### Тестирование

Тесты на `pytest` в [tests/](tests/). Фикстура `db_session` (в [tests/conftest.py](tests/conftest.py)) переинициализирует фабрику на in-memory SQLite через `db_sessions._reset_for_tests()` + `global_init(":memory:")`. Тесты с маршрутами создают приложение через `create_app(":memory:")` и используют `app.test_client()`.

### Неиспользуемый код

- В [data/user_api.py](data/user_api.py) объявлен REST-блюпринт, но он **не зарегистрирован** в `main.py` и обращается к полям (`about`), которых нет в модели `User`. Считай это мёртвым кодом, пока явно не работаешь над API.
- В [forms/user.py](forms/user.py) есть `RegisterForm` (Flask-WTF), но `/register` парсит `request.form` напрямую и форму не использует.
- Шаблон [templates/chats.html](templates/chats.html) больше не используется (лента теперь под `/contacts/<id>`), но оставлен на случай если понадобится откатить.

## Соглашения, которые стоит сохранять

- Все строки, обращённые к пользователю (шаблоны, сообщения об ошибках, отладочные `print`), — на русском. При правках сохраняй язык.
- Шаблоны несогласованы: [base.html](templates/base.html), [code.html](templates/code.html), [register.html](templates/register.html), [login.html](templates/login.html), [contacts.html](templates/contacts.html), [contacts_manage.html](templates/contacts_manage.html) используют Bootstrap 5 и Jinja-наследование от `base.html`; [index.html](templates/index.html) и [chats.html](templates/chats.html) — самостоятельные, со своим инлайн-`<style>`. Не предполагай, что шаблон расширяет `base.html`, не проверив.
- `SECRET_KEY` захардкожен как `'yandexlyceum_secret_key'` (это учебный проект Яндекс Лицея). Не меняй его без согласования с пользователем.
