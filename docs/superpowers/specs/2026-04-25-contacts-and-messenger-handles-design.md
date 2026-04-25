# Контакты и связывание личностей из мессенджеров

**Дата:** 2026-04-25
**Статус:** утверждено

## Контекст

Сейчас уведомления, прилетающие с устройства MacroDroid в `POST /add`, складываются в одну общую таблицу `Messages` и отображаются на странице `/messages` единой лентой, отсортированной по `id` убыванием. Сообщения никак не группируются по реальному человеку: одно и то же лицо в Telegram и в Max выглядит как два разных «отправителя», между ними нет связи.

Цель этой работы — перейти к **контакт-центричной** модели:

- Сообщение принадлежит **контакту** (реальному человеку с точки зрения владельца аккаунта), а не строке `sender`.
- У одного контакта может быть несколько «личностей» (handles) в разных мессенджерах. Один Contact агрегирует все личности и все сообщения этого человека.
- UI: слева — список контактов; справа, при выборе контакта, — общая лента сообщений со всеми его личностями (Telegram, Max, и т.д.) вперемешку, с пометкой источника у каждого сообщения.
- Отдельная страница управления связями: переименование, перемещение личности между контактами, слияние двух контактов в один.
- Программа сама **подсказывает** возможные слияния по похожим именам, но финальное решение всегда за пользователем.

## Терминология

| Термин | Что значит |
|---|---|
| **User** | Владелец аккаунта на сайте (тот, кто зарегистрировался). |
| **Contact** | Реальный человек глазами `User`. У одного `User` много контактов. |
| **MessengerHandle (handle)** | Конкретная личность контакта в конкретном мессенджере. У одного `Contact` может быть много handles, но один handle принадлежит ровно одному `Contact`. |
| **Sender** | Строка с именем отправителя из уведомления MacroDroid. Сама по себе не является сущностью БД — попадает в `MessengerHandle.sender_raw`. |

## Допущения

1. **Идентификатор отправителя** — пара `(messenger_name, sender)`. Стабильного ID (типа `telegram_user_id` или номера телефона) у нас нет, потому что MacroDroid отдаёт только текст уведомления. Если человек переименовался в мессенджере — придёт «новая личность», пользователь её домерджит руками через панель управления.
2. **Групповые чаты** не поддерживаются как отдельная сущность. Если уведомление пришло из группы и `sender = "Иван"`, оно привязывается к контакту с этим именем как и любое личное сообщение. Различение «личка vs. группа» — за рамками этой работы.
3. **Каждое новое `(messenger_name, sender)` автоматически создаёт `MessengerHandle` и неприсвоенный `Contact`** с `display_name = sender`. Сообщение сразу присваивается. Сливать контакты пользователь может потом вручную или приняв подсказку.
4. **Алгоритм похожести имён** — `difflib.SequenceMatcher.ratio()` поверх нормализованных имён, порог сходства `0.7`. Без новых зависимостей.
5. **Live-обновления** остаются как сейчас — meta-refresh каждые 5 секунд. WebSocket / SSE — за рамками.
6. **Reply из веба обратно в мессенджер** — за рамками. Только просмотр.
7. **Существующие сообщения в БД мигрируются** одноразовым скриптом: для каждой уникальной тройки `(user_id, messenger_name, sender)` создаётся handle + contact, сообщения переподвязываются.
8. **Авторизация** не меняется: остаётся session-based, как сейчас.

## Архитектура

### Модель данных

```
User
  └─ 1:N → Contact(id, user_id, display_name, created_at)
              └─ 1:N → MessengerHandle(id, contact_id, user_id, messenger_name, sender_raw, sender_normalized, created_at)
                          └─ 1:N → Messages(... , handle_id, created_at)

User
  └─ 1:N → MergeSuggestion(id, user_id, source_handle_id, target_contact_id, score, status, created_at)
```

#### Contact

| Поле | Тип | Примечание |
|---|---|---|
| `id` | `Integer PK` | autoincrement |
| `user_id` | `Integer FK→users.id` | владелец |
| `display_name` | `String` | редактируется пользователем; начальное значение — `sender_raw` первого handle |
| `created_at` | `DateTime` | `default=datetime.now` |

#### MessengerHandle

| Поле | Тип | Примечание |
|---|---|---|
| `id` | `Integer PK` | |
| `contact_id` | `Integer FK→contacts.id` | |
| `user_id` | `Integer FK→users.id` | денормализован для быстрого лукапа в `/add` без JOIN |
| `messenger_name` | `String` | например `"Telegram"`, `"Max"` |
| `sender_raw` | `String` | как пришло из MacroDroid |
| `sender_normalized` | `String` | результат нормализации (см. §«Автомэтчинг») |
| `created_at` | `DateTime` | |

UNIQUE constraint: `(user_id, messenger_name, sender_raw)`.

#### Messages

Существующие поля (`id`, `sender`, `text`, `messenger_name`, `time`, `user_id`) **сохраняются** — это «снимок» того, что прилетело из уведомления. Если sender в Telegram переименуется — мы хотим помнить старое имя в исторических сообщениях.

Добавляются:

| Поле | Тип | Примечание |
|---|---|---|
| `handle_id` | `Integer FK→messenger_handles.id`, NULLable | После миграции — заполнен у всех. |
| `created_at` | `DateTime` | Полноценный timestamp. Поле `time: String '%H:%M'` остаётся для отображения, но сортировка/группировка идёт по `created_at`. |

#### MergeSuggestion

| Поле | Тип | Примечание |
|---|---|---|
| `id` | `Integer PK` | |
| `user_id` | `Integer FK→users.id` | владелец предложения |
| `source_handle_id` | `Integer FK→messenger_handles.id` | новый handle, для которого ищем «похожих» |
| `target_contact_id` | `Integer FK→contacts.id` | существующий контакт, к которому предлагается приклеить |
| `score` | `Float` | значение `SequenceMatcher.ratio()` |
| `status` | `String` | `pending` / `accepted` / `dismissed` |
| `created_at` | `DateTime` | |

UNIQUE constraint: `(source_handle_id, target_contact_id)` — одно и то же предложение не дублируем.

### Поток `POST /add`

```
POST /add (sender, text, messenger_name)
  1. Валидация: все три поля непустые → иначе 400.
  2. user ← User by tablet_ip == request.remote_addr.
     Не нашли → 200 + лог "Неизвестное устройство" (как сейчас).
  3. sender_normalized ← normalize(sender)   (см. §«Автомэтчинг»)
  4. handle ← MessengerHandle by (user.id, messenger_name, sender_raw=sender).
  5. Если handle не найден:
       a) contact ← новый Contact(user_id=user.id, display_name=sender)
       b) handle  ← новый MessengerHandle(contact, user.id, messenger_name,
                                          sender_raw=sender, sender_normalized)
       c) flush, чтобы у handle и contact появились id
       d) suggest_merges_for_handle(handle)   (см. §«Автомэтчинг»)
  6. message ← Messages(sender, text, messenger_name, time=HH:MM,
                       user_id=user.id, handle_id=handle.id, created_at=now())
  7. commit.
  8. 200 OK.
```

Ошибка при создании: rollback и 500. Сейчас в проекте нет глобального error handler — добавим узкий try/except вокруг шагов 4–7.

### UI и маршруты

Старый `/messages` → 302 redirect на `/contacts`.

| Маршрут | Метод | Назначение |
|---|---|---|
| `/contacts` | GET | Двухпанельный лейаут. Слева — список контактов, отсортированный по последнему сообщению (по `MAX(Messages.created_at)`). Справа — заглушка «выберите контакт». |
| `/contacts/<contact_id>` | GET | То же, но справа — лента сообщений выбранного контакта (все handles вперемешку, отсортировано по `Messages.created_at` убыванием), у каждого сообщения подпись `[messenger_name]` и `[sender_raw]` (если у контакта несколько handles в одном мессенджере — это полезно). |
| `/contacts/manage` | GET | Панель управления: таблица всех handles пользователя с указанием контакта; блок «Подсказки слияния» (`MergeSuggestion.status == 'pending'`). |
| `/contacts/<contact_id>/rename` | POST | Переименовать `display_name`. |
| `/contacts/merge` | POST | Тело: `source_id`, `target_id`. Все handles `source` → `target`, source-Contact удаляется. |
| `/contacts/handles/<handle_id>/move` | POST | Тело: `target_contact_id` (или флаг «новый контакт»). Перемещает handle. |
| `/contacts/suggestions/<id>/accept` | POST | Принимает подсказку: запускает merge `source_handle.contact_id` → `target_contact_id`. Помечает `status=accepted`. |
| `/contacts/suggestions/<id>/dismiss` | POST | Помечает `status=dismissed`. |

Все маршруты `/contacts*` защищены проверкой `session.get('user_id')`. Доступ к чужим контактам/handles/suggestions — 404.

### Шаблоны

- `templates/contacts.html` — наследует `base.html`. Bootstrap row: `col-md-4` (список контактов) + `col-md-8` (лента). Принимает в контексте `contacts: List[Contact]`, `selected: Optional[Contact]`, `messages: Optional[List[Messages]]`.
- `templates/contacts_manage.html` — наследует `base.html`. Таблица handles + блок предложений с кнопками «Объединить» / «Скрыть».
- Сохраняем meta-refresh каждые 5 секунд на `/contacts*` страницах (как в текущем `chats.html`).
- Тексты — на русском.

## Автомэтчинг

### Нормализация имени

Функция `normalize(s: str) -> str` в `data/matching.py`:

1. `s.lower()`
2. `s.strip()`
3. Удалить emoji (по unicode-категории `So` / regex `\p{Emoji}` через `re` с unicode property).
4. Удалить все символы, кроме букв (любого алфавита) и цифр.
5. Схлопнуть множественные пробелы (фактически после шага 4 пробелов не останется, но шаг идёт для устойчивости).

### Расчёт сходства

`similarity_score(a_norm: str, b_norm: str) -> float` = `difflib.SequenceMatcher(None, a_norm, b_norm).ratio()`.

Порог по умолчанию `MATCH_THRESHOLD = 0.7` — константа в `data/matching.py`. При желании пользователь сможет крутить позже; сейчас не выносим в UI.

### Когда генерируем подсказки

Шаг 5d в `/add`: после создания нового handle проходимся по всем `MessengerHandle` того же `user_id` с другим `contact_id`. Для каждого, чей `similarity_score(new.sender_normalized, other.sender_normalized) ≥ MATCH_THRESHOLD`, создаём `MergeSuggestion(source_handle_id=new.id, target_contact_id=other.contact_id, score, status='pending')`.

Если такая запись уже есть (UNIQUE constraint) — не создаём.

### Жизненный цикл предложения

- `pending` → отображается на `/contacts/manage`.
- `accepted` → выполнен merge, остаётся в БД для аудита.
- `dismissed` → пользователь скрыл, больше не показываем.

При merge-операции (как через accept, так и через ручной merge) все «висящие» pending-предложения становятся неактуальными и помечаются как `dismissed`, если они ссылаются:
- на удаляемый source-Contact (как `target_contact_id`),
- на любой из его handles (как `source_handle_id`),
- либо на target-Contact в роли `source_handle_id` (т.е. handle уже принадлежит контакту, в который мы вливаем — предложение бессмысленно).

## Миграция данных

Одноразовая функция `data/migrations.py::migrate_to_contacts_v1()`:

1. `SqlAlchemyBase.metadata.create_all(engine)` создаёт новые таблицы (`contacts`, `messenger_handles`, `merge_suggestions`).
2. Для SQLite добавление новой колонки в `Messages` — через `ALTER TABLE messages ADD COLUMN handle_id INTEGER` и `ADD COLUMN created_at DATETIME`. Скрипт делает это вручную (SQLAlchemy не делает ALTER автоматически).
3. Группируем существующие `Messages` по `(user_id, messenger_name, sender)`. Для каждой группы:
   - Создаём `Contact(user_id, display_name=sender)`.
   - Создаём `MessengerHandle(contact_id, user_id, messenger_name, sender_raw=sender, sender_normalized=normalize(sender))`.
   - У всех `Messages` группы проставляем `handle_id`. `created_at` ставим в `datetime.now()` — точное время уже не восстановить, поле `time` остаётся как было.
4. Логируем сколько контактов/handles создано.

Запуск: `python -m data.migrations`. Идемпотентность: при повторном вызове — проверять, есть ли уже handles, не создавать дубликаты.

Скрипт **не запускает** автомэтчинг для исторических данных — это перегрузило бы UI кучей предложений сразу. Подсказки начинают накапливаться только для новых сообщений после миграции.

## Обработка ошибок

| Ситуация | Реакция |
|---|---|
| `/add` без поля `sender`/`text`/`messenger_name` | 400 (сейчас приложение молча создаёт пустую запись — чиним заодно). |
| `/add` с `remote_addr`, не привязанным к пользователю | 200 + лог `"Неизвестное устройство с IP: ..."` (как сейчас). |
| `/contacts/<id>` чужого пользователя или несуществующий | 404. |
| `merge` с одинаковыми `source_id == target_id` | 400. |
| `merge`, где `source` и `target` принадлежат разным `User` | 404. |
| `move` handle на чужой `target_contact_id` | 404. |

## Тесты

В проекте сейчас тестов нет. Добавляем `pytest` в `.venv` и минимальный набор:

- `tests/test_matching.py`
  - `normalize` обрабатывает emoji, регистр, пробелы, кириллицу/латиницу.
  - `similarity_score` возвращает 1.0 для одинаковых строк, 0.0 для совсем разных.
  - Известные пары имён: `"Ivan"` ≈ `"иван"` (после нормализации идентичны → 1.0); `"Иван П."` vs `"Ivan P"` — ниже порога (другой алфавит); `"Vanya"` vs `"Ваня"` — ниже порога. Эти кейсы документируем как known limitation: транслит мы не покрываем.
- `tests/test_add_endpoint.py`
  - Первое сообщение от нового sender → создаётся Contact + Handle, Messages.handle_id заполнен.
  - Повторное сообщение того же sender → handle переиспользован, новый Contact не создан.
  - `/add` без полей → 400.
  - `/add` без привязанного устройства → 200 + ничего не записано.
- `tests/test_merge.py`
  - Merge переподвязывает handles, удаляет source-Contact, не трогает чужих пользователей.
  - Pending-предложения, ссылающиеся на удаляемый Contact, помечаются `dismissed`.
- `tests/test_suggestions.py`
  - При создании нового handle с похожим именем создаётся `MergeSuggestion(pending)`.
  - При создании handle с непохожим именем — не создаётся.
  - Дубликаты (UNIQUE) не создаются.

Конфигурация теста: SQLite in-memory (`sqlite:///:memory:`), отдельный `db_sessions.global_init` per-test через фикстуру.

Тесты заодно подсветят, что общая `db_sess` в `main.py:18` не годится для тестового окружения — это станет аргументом за её рефакторинг (но не в этой работе).

## Изменения в файлах проекта

**Новые:**
- `data/contacts.py` — модели `Contact`, `MessengerHandle`, `MergeSuggestion`.
- `data/matching.py` — `normalize`, `similarity_score`, `MATCH_THRESHOLD`, `suggest_merges_for_handle`.
- `data/migrations.py` — `migrate_to_contacts_v1`, точка входа `if __name__ == "__main__"`.
- `templates/contacts.html`, `templates/contacts_manage.html`.
- `tests/` (создаём с нуля), `tests/conftest.py` с фикстурами.

**Меняются:**
- `data/__all_models.py` — добавить `from . import contacts`.
- `data/users.py` — добавить колонки `Messages.handle_id`, `Messages.created_at`. Удалить закомментированный `Chats`.
- `main.py` — зарегистрировать новые маршруты `/contacts*`, переписать `/add` под новую логику, оставить `/messages → /contacts` редиректом.
- `CLAUDE.md` — обновить раздел про модель данных и upcoming архитектуру (в самом конце работы, отдельным шагом).

**Не трогаем:**
- `data/user_api.py` (мёртвый код, остаётся как есть).
- `forms/user.py` (тоже не используется).
- Глобальная `db_sess` в `main.py:18` (отдельный refactor).
- `SECRET_KEY`, авторизация.

## За рамками

- Reply из веба обратно в мессенджер.
- Поиск/фильтр в списке контактов.
- WebSocket / SSE для live-обновлений.
- Поддержка групповых чатов как отдельной сущности (на уровне UI и модели).
- Транслит-нормализация (Vanya ≈ Ваня).
- Рефакторинг общей `db_sess`.
- Аватары контактов, заметки.
- Экспорт переписки.
