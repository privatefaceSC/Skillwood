# Группировка handles по двоеточию (групповые чаты)

**Дата:** 2026-05-12
**Ветка:** feature/contacts
**Контекст:** Сейчас Telegram и Max шлют уведомления групповых чатов в формате `"X: Y"` / `"X:Y"`, где `X` — название группы, `Y` — имя автора. Skillwood сохраняет это как `sender_raw` целиком и заводит на каждого автора отдельный `Contact`. В результате один групповой чат «9б класс» превращается в десятки одиночных контактов («9б класс: Софья Гоева», «9б класс: Вика Воропаева» и т.д.). Нужно автоматически объединять их в один Contact «9б класс» и показывать автора внутри переписки.

## Решение в одном предложении

В `find_or_create_handle` добавляем ветку: если `sender_raw` разбирается как `"prefix:member"` и среди существующих handles того же пользователя есть **другой** handle с тем же `prefix` — все handles этого префикса (старые и новый) переподвязываются на единый Contact с `display_name = prefix`. Опустевшие одиночные Contact'ы удаляются. Та же логика — одноразовым скриптом для исторических данных. В шаблоне переписки имя автора печатается без префикса.

## Архитектура

Логика живёт в трёх местах:

1. **Парсер** в [data/matching.py](../../../data/matching.py) — чистая stdlib-функция.
2. **Промоушн** в [data/contacts.py](../../../data/contacts.py) — внутри `find_or_create_handle` перед обычной веткой «создаём Contact с `display_name=sender_raw`».
3. **Миграция** в [data/migrations.py](../../../data/migrations.py) — одноразовая функция, повторяющая логику промоушна для всей таблицы. CLI-диспатч принимает имя функции.

Шаблон [templates/contacts.html](../../../templates/contacts.html) и JSON-эндпоинт `/contacts/<id>/messages.json` показывают имя автора, отрезав префикс контакта.

## Компонент 1: парсер префикса

```python
# data/matching.py

def split_group_sender(sender_raw: str) -> tuple[str, str] | None:
    """Разобрать sender_raw как 'X: Y' / 'X:Y'.

    Сплит по ПЕРВОМУ двоеточию (partition), чтобы 'Время: 10:30' дало
    ('Время', '10:30'), а не отрезалось дальше. Возвращает None, если
    двоеточия нет, либо после strip() prefix или member пустые.
    """
    if ":" not in sender_raw:
        return None
    prefix, _, member = sender_raw.partition(":")
    prefix, member = prefix.strip(), member.strip()
    if not prefix or not member:
        return None
    return prefix, member
```

Stdlib-only, никаких новых зависимостей.

## Компонент 2: промоушн в `find_or_create_handle`

Сейчас структура функции:

```
if handle exists for (user_id, messenger, sender_raw): return handle, False
create Contact(display_name=sender_raw), flush
create MessengerHandle, flush
suggest_merges_for_handle(handle)
return handle, True
```

Меняется на:

```
if handle exists for (user_id, messenger, sender_raw): return handle, False

parsed = split_group_sender(sender_raw)
if parsed is not None:
    prefix, _member = parsed
    siblings = [
        h for h in db.query(MessengerHandle).filter(MessengerHandle.user_id == user_id).all()
        if h.sender_raw != sender_raw
           and (p := split_group_sender(h.sender_raw)) is not None
           and p[0] == prefix
    ]
    if siblings:
        sibling_contact_ids = {h.contact_id for h in siblings}
        if len(sibling_contact_ids) == 1:
            # уже промоушенный групповой Contact — присоединяемся
            group_contact_id = next(iter(sibling_contact_ids))
        else:
            # первый промоушн: создаём групповой Contact, стягиваем все handles
            group_contact = Contact(user_id=user_id, display_name=prefix)
            db.add(group_contact)
            db.flush()
            group_contact_id = group_contact.id
            moved_handle_ids = []
            old_contact_ids = set()
            for h in siblings:
                old_contact_ids.add(h.contact_id)
                h.contact_id = group_contact_id
                moved_handle_ids.append(h.id)
            db.flush()
            # чистка опустевших Contact'ов и связанных MergeSuggestion
            for old_id in old_contact_ids:
                remaining = db.query(MessengerHandle).filter(MessengerHandle.contact_id == old_id).count()
                if remaining == 0:
                    # помечаем dismissed pending-suggestions, ссылающиеся на удаляемый Contact
                    # либо на любой из перетащенных handles — по аналогии с merge_contacts
                    conditions = [MergeSuggestion.target_contact_id == old_id]
                    if moved_handle_ids:
                        conditions.append(MergeSuggestion.source_handle_id.in_(moved_handle_ids))
                    db.query(MergeSuggestion).filter(
                        MergeSuggestion.status == "pending",
                        sqlalchemy.or_(*conditions),
                    ).update({MergeSuggestion.status: "dismissed"}, synchronize_session=False)
                    db.query(Contact).filter(Contact.id == old_id).delete(synchronize_session=False)
            db.flush()
        handle = MessengerHandle(
            contact_id=group_contact_id,
            user_id=user_id,
            messenger_name=messenger_name,
            sender_raw=sender_raw,
            sender_normalized=normalize(sender_raw),
        )
        db.add(handle)
        db.flush()
        # suggest_merges_for_handle НЕ зовём: мы уже в правильном Contact'е
        return handle, True

# обычный путь: нет двоеточия ИЛИ нет сиблингов
contact = Contact(user_id=user_id, display_name=sender_raw)
db.add(contact); db.flush()
handle = MessengerHandle(...); db.add(handle); db.flush()
suggest_merges_for_handle(db, handle)
return handle, True
```

Ключевые инварианты:

- **Поиск сиблингов в Python**, не в SQL — у одного пользователя сотни handles, не сотни тысяч; SQL для partition пришлось бы делать через `instr`/`substr`, что хрупко и нечитаемо.
- **`messenger_name` не сужает поиск**: групповой чат «9б класс» в Telegram и в Max — это одна группа, должна стать одним Contact'ом.
- **Чистка опустевших Contact'ов** — `MergeSuggestion` с `target_contact_id` = удаляемый помечаются dismissed, чтобы UI на `/contacts/manage` не показывал ссылки на несуществующий контакт. Логика повторяет `merge_contacts`.
- **`suggest_merges_for_handle` не вызывается** для handles, попавших в группу: эта эвристика рассчитана на похожие имена реальных людей, а внутри группы все handles по определению похожи на префикс, что даёт мусорные предложения.

## Компонент 3: миграционный скрипт

Новая функция в [data/migrations.py](../../../data/migrations.py):

```python
def migrate_group_handles_v1(db) -> dict:
    """Найти handles с префиксом и склеить их в групповые Contact'ы.

    Идемпотентна. Запускать после migrate_to_contacts_v1.
    Возвращает {"groups_created", "handles_moved", "contacts_removed"}.
    """
```

Алгоритм:

```
для каждого user_id из таблицы users:
    handles = все MessengerHandle с user_id
    groups: dict[prefix -> list[handle]] = группируем по split_group_sender(h.sender_raw)[0]
    (handles без префикса пропускаем)

    для каждого (prefix, hs) с len(hs) >= 2:
        # проверяем, не объединены ли они уже в один Contact
        contact_ids = {h.contact_id for h in hs}

        # ищем существующий групповой Contact: тот, у которого display_name == prefix
        # И ссылаются на него только handles с этим префиксом
        existing_group = db.query(Contact).filter(
            Contact.user_id == user_id,
            Contact.display_name == prefix,
        ).first()

        if existing_group and len(contact_ids) == 1 and next(iter(contact_ids)) == existing_group.id:
            continue  # уже всё ок

        target_id = existing_group.id if existing_group else None
        if target_id is None:
            group_contact = Contact(user_id=user_id, display_name=prefix)
            db.add(group_contact); db.flush()
            target_id = group_contact.id
            groups_created += 1

        moved_handle_ids = []
        old_contact_ids = set()
        для h в hs если h.contact_id != target_id:
            old_contact_ids.add(h.contact_id)
            h.contact_id = target_id
            moved_handle_ids.append(h.id)
            handles_moved += 1
        db.flush()

        для old_id в old_contact_ids:
            если в этом Contact'е больше нет handles:
                почистить MergeSuggestion как в промоушне
                db.delete(Contact[old_id])
                contacts_removed += 1

db.commit()
return {"groups_created": ..., "handles_moved": ..., "contacts_removed": ...}
```

CLI: расширяем `__main__` в `data/migrations.py`, чтобы принимал имя функции:

```python
if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "migrate_to_contacts_v1"
    func = globals().get(name)
    if func is None or not callable(func):
        print(f"Неизвестная миграция: {name}")
        sys.exit(1)
    db_sessions.global_init("db/blogs.db")
    session = db_sessions.create_session()
    try:
        stats = func(session)
        print(f"Миграция {name} завершена: {stats}")
    finally:
        session.close()
```

Обратная совместимость: `python -m data.migrations` без аргумента продолжает запускать `migrate_to_contacts_v1`.

## Компонент 4: отображение в шаблоне

Сейчас [templates/contacts.html](../../../templates/contacts.html) рендерит каждое сообщение как:

```html
<span class="source">{{ m.messenger_name }} · {{ m.sender }}</span>
```

`m.sender` хранит `sender_raw` целиком. Для контакта «9б класс» с handle «9б класс: Софья Гоева» это даёт «Telegram · 9б класс: Софья Гоева» — лишний шум.

Правило: если `m.sender.startswith(selected.display_name + ":")` — отрезаем префикс и двоеточие, делаем `strip()`. Иначе показываем `m.sender` как есть.

Для удобства добавляем серверный хелпер в `data/matching.py`:

```python
def display_author(sender_raw: str, contact_display_name: str) -> str:
    """Вернуть имя автора без префикса группы.

    Если sender_raw начинается с 'contact_display_name:' (любая комбинация
    с пробелами вокруг двоеточия) — отрезаем и strip. Иначе возвращаем sender_raw.
    """
```

В роутах `contact_detail` и `contact_messages_json` после получения сообщений проставляем `m.display_author` на каждом (через присвоение атрибута на SQLAlchemy-объект — он не commit'ится, только живёт в сессии до конца запроса). JSON-ответ получает поле `display_author`. Jinja и JS используют `m.display_author` напрямую.

## Тестирование

Новый файл `tests/test_group_grouping.py`. Покрытие:

**Парсер:**
- `split_group_sender("9б класс: Софья Гоева")` → `("9б класс", "Софья Гоева")`
- `split_group_sender("9б класс:Софья Гоева")` → то же
- `split_group_sender("Время: 10:30 PM")` → `("Время", "10:30 PM")` (сплит по первому двоеточию)
- `split_group_sender("Софья")` → `None`
- `split_group_sender(":Софья")` → `None`
- `split_group_sender("Софья:")` → `None`
- `split_group_sender("  :  ")` → `None`

**Промоушн через `find_or_create_handle`:**
1. Первый handle с префиксом → обычный Contact с `display_name == sender_raw`, без группы.
2. Второй handle с тем же префиксом → создан групповой Contact `display_name == prefix`, оба handles теперь под ним, старый одиночный Contact удалён, сообщения первого handle продолжают читаться через `record_message → handle → group Contact`.
3. Третий handle с тем же префиксом → присоединяется к существующему групповому, ничего не создаётся и не удаляется.
4. Кросс-messenger: первый handle в `Telegram`, второй в `Max`, оба с префиксом «9б класс» → один групповой Contact.
5. Кросс-юзер: handle с префиксом «9б класс» у user 1 и у user 2 → не склеиваются, два разных Contact'а.
6. Параллельный префикс «9б класс: » (с пробелом) и «9б класс:» (без) → склеиваются (после `strip()` префиксы равны).
7. Чистка `MergeSuggestion`: если на handle, попавший в группу, висел pending-suggestion → он становится dismissed; если на handle указывала suggestion как target → тоже dismissed.

**Хелпер `display_author`:**
- `display_author("9б класс: Софья", "9б класс")` → `"Софья"`
- `display_author("9б класс:Софья", "9б класс")` → `"Софья"`
- `display_author("Иван Иванов", "Иван Иванов")` → `"Иван Иванов"`
- `display_author("Doctor:Strange", "Кто-то другой")` → `"Doctor:Strange"` (префикс не совпадает)

**Маршруты:**
- `GET /contacts/<id>` для группового контакта возвращает страницу, в HTML которой имя автора отображается без префикса (проверяем через `b"Софья" in resp.data and b"9б класс: Софья" not in resp.data`).
- `GET /contacts/<id>/messages.json` для группового контакта возвращает `display_author` без префикса.

**Миграция:**
- Сценарий: руками создаём 3 одиночных Contact'а с handles «9б класс: A», «9б класс: B», «9б класс: C» (как было до фичи). Запускаем `migrate_group_handles_v1`. Проверяем: появился групповой Contact «9б класс», все 3 handles там, 3 старых Contact'а удалены.
- Идемпотентность: повторный запуск возвращает все нули.
- Сценарий с одиночным handle «X: Y», где X встречается всего один раз → миграция его не трогает.
- Сценарий с существующим групповым Contact'ом + новые одиночки с тем же префиксом → миграция дотягивает их в существующий, нового Contact'а не создаёт.

## Что НЕ делаем

- Не вводим понятие «group/individual» в схему БД. Групповой характер Contact'а — производное (один или больше handles, имеющих общий префикс == `display_name`).
- Не предупреждаем при ручном переименовании: если пользователь переименует группу «9б класс» в «Школа», новый handle «9б класс: D» создаст ещё один Contact «9б класс» (потому что среди существующих handles группы все handles остались с префиксом «9б класс», переименовался только Contact). Это редкий кейс, лечится ручным merge через `/contacts/manage`.
- Не делаем разделители `/`, `—`, `|` — только двоеточие.
- Не показываем сейчас (вариант (б)) «имя автора только когда сменился» и (в) с цветными плашками. Базово — имя над каждым бабблом (вариант (а)).
- Не запускаем `suggest_merges_for_handle` на групповых handles.

## Файлы и точки изменений

- [data/matching.py](../../../data/matching.py) — `+split_group_sender`, `+display_author`.
- [data/contacts.py](../../../data/contacts.py) — расширить `find_or_create_handle`, импорт `Contact, MergeSuggestion` и `split_group_sender`.
- [data/migrations.py](../../../data/migrations.py) — `+migrate_group_handles_v1`, переписать `__main__` на диспатч по имени.
- [main.py](../../../main.py) — в `contact_detail` и `contact_messages_json` проставлять `display_author` на каждом сообщении.
- [templates/contacts.html](../../../templates/contacts.html) — Jinja-ветка использует `m.display_author`, JS-рендер использует `m.display_author` из JSON.
- `tests/test_group_grouping.py` — новый.
