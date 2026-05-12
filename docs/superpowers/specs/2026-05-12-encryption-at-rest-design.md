# Шифрование сообщений в БД (encryption at rest)

**Дата:** 2026-05-12
**Ветка:** feature/contacts
**Контекст:** Skillwood планируется выкатить в публичный интернет с открытой регистрацией. Сейчас текст сообщений лежит в `db/blogs.db` в открытом виде. Цель — чтобы при прямом просмотре файла БД (`sqlite3 db/blogs.db`, DB Browser, утечка backup'а, SQL injection) сообщения выглядели как шифротекст и не читались. При нормальной работе сайта через веб-интерфейс пользователь видит свои сообщения как обычно.

Это **уровень (б0)** из обсуждения: один симметричный ключ на весь сервер, лежит в env-переменной. Защищает от утечки файла БД и любопытных глаз, **не защищает** от админа с SSH-доступом к серверу (он видит и БД, и env, и код).

## Решение в одном предложении

Добавляем `data/crypto.py` с парой `encrypt/decrypt` на базе `cryptography.Fernet`, ключ из `SKILLWOOD_ENCRYPTION_KEY` (с dev-fallback). `Messages.text` теперь использует SQLAlchemy `TypeDecorator` `EncryptedText`, который автоматически шифрует на запись и расшифровывает на чтение. Прикладной код этого не видит — `m.text` остаётся обычной строкой. Миграционный скрипт зашифровывает существующие сообщения.

## Архитектура

### Компонент 1: `data/crypto.py`

```python
import os
from cryptography.fernet import Fernet, InvalidToken
import sqlalchemy.types as types

_PREFIX = "enc:v1:"
# Используется только при отсутствии env-переменной — для локальной разработки и тестов.
# В проде ставим SKILLWOOD_ENCRYPTION_KEY=... (44-символьный fernet-ключ).
_DEV_KEY = "qkrCQOcCWmDg4ULLcQc6_J6Zi8hO_VSm3X_zXJL7vMc="

def _key() -> bytes:
    return (os.environ.get("SKILLWOOD_ENCRYPTION_KEY") or _DEV_KEY).encode("ascii")

def _cipher() -> Fernet:
    return Fernet(_key())

def encrypt(plaintext):
    if plaintext is None:
        return None
    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + token

def decrypt(value):
    if value is None or not isinstance(value, str):
        return value
    if not value.startswith(_PREFIX):
        return value  # обратная совместимость со старыми незашифрованными строками
    try:
        return _cipher().decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return value  # повреждённое или из другого ключа — не валим, возвращаем как есть

class EncryptedText(types.TypeDecorator):
    impl = types.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)
```

### Компонент 2: `Messages.text` использует `EncryptedText`

В [data/users.py](../../../data/users.py): `text = sqlalchemy.Column(sqlalchemy.String)` → `text = sqlalchemy.Column(EncryptedText())`. Один импорт + один тип. Никаких других моделей не трогаем.

Поля `sender`, `messenger_name` остаются в открытом виде (имя отправителя/мессенджера — менее чувствительная информация, и расшифровка на каждый список контактов сильно дороже).

### Компонент 3: миграционный скрипт

`migrate_encrypt_messages_v1(db)` в [data/migrations.py](../../../data/migrations.py). Алгоритм:

```python
def migrate_encrypt_messages_v1(db):
    from .crypto import encrypt, _PREFIX
    rows = db.execute(sqlalchemy.text("SELECT id, text FROM messages")).fetchall()
    encrypted = 0
    for row_id, text in rows:
        if text is None or text.startswith(_PREFIX):
            continue
        new_text = encrypt(text)
        db.execute(
            sqlalchemy.text("UPDATE messages SET text = :t WHERE id = :i"),
            {"t": new_text, "i": row_id},
        )
        encrypted += 1
    db.commit()
    return {"encrypted": encrypted}
```

**Важно:** используем raw SQL, потому что `EncryptedText.process_result_value` уже расшифрует на load, а `process_bind_param` на save снова зашифрует → получим двойное шифрование. Raw SQL обходит TypeDecorator.

Идемпотентность: пропускаем сообщения, уже начинающиеся с `enc:v1:`.

### Компонент 4: совместимость со старыми данными

`decrypt` не валится на строках без префикса `enc:v1:` — просто возвращает как есть. То есть до миграции старые plaintext-сообщения продолжают читаться. После миграции — все зашифрованы. Это нужно, чтобы релиз был ленивым: можно выкатить код, всё работает, потом запустить миграцию.

## Тесты

Новый файл `tests/test_crypto.py`:

- `encrypt(x) != x` (не plaintext)
- `encrypt(x).startswith("enc:v1:")` (правильный префикс)
- `decrypt(encrypt(x)) == x` (round-trip)
- `decrypt(plaintext_without_prefix) == plaintext_without_prefix` (обратная совместимость)
- `decrypt(None) is None`, `encrypt(None) is None`
- Длинная строка (1024+ символов) шифруется-расшифровывается
- Юникод/эмодзи: `encrypt("привет 🚀")` round-trip
- Корректное поведение, когда сами ключи разные — `decrypt` возвращает значение как есть (через `InvalidToken`-ветку), а не валится

`tests/test_messages_encryption.py`:

- `record_message` шифрует на запись: `db.execute("SELECT text FROM messages").first()[0].startswith("enc:v1:")` истинно
- `m.text` через ORM читается как plaintext (TypeDecorator расшифровал)
- Существующие тесты на `m.text == "привет"` продолжают работать — это критерий, что TypeDecorator прозрачный

`tests/test_migration.py` (расширение):

- `migrate_encrypt_messages_v1`: создаём 3 сообщения plaintext-вставкой через raw SQL, прогоняем миграцию, проверяем что все начинаются с `enc:v1:`
- Идемпотентность: повторный запуск возвращает `{"encrypted": 0}`
- Сообщения с уже зашифрованным текстом не трогаются

## Что НЕ делаем

- Не шифруем `sender`, `messenger_name`, `time` — они менее чувствительны.
- Не шифруем `display_name` контактов (имена тоже потенциально чувствительные, но для них шифрование сильно дороже из-за поиска/сортировки в UI; отдельный сабпроект, если понадобится).
- Не делаем пер-юзерные ключи. Это уровень (б+) — отдельная история, если когда-нибудь решим, что админу читать нельзя.
- Не делаем ротацию ключа (key versioning) — `enc:v1:` префикс оставляет место для v2, но реализацию ротации добавим, когда понадобится.
- Не шифруем `OutgoingQueue` на Android-стороне — там сообщения и так короткоживущие, в очереди на устройстве пользователя.

## Файлы

Новые:
- `data/crypto.py`
- `tests/test_crypto.py`
- `tests/test_messages_encryption.py`

Изменения:
- `data/users.py` — `Messages.text` использует `EncryptedText`
- `data/migrations.py` — `+migrate_encrypt_messages_v1`
- `requirements.txt` — `+cryptography`

## Развёртывание

1. Сгенерировать ключ: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Сохранить.
2. Положить в env-переменную сервера: `SKILLWOOD_ENCRYPTION_KEY=<тот ключ>`.
3. Запустить миграцию: `python -m data.migrations migrate_encrypt_messages_v1`.
4. Перезапустить сервер.

**Если ключ потерять — все зашифрованные сообщения нечитаемы навсегда.** Хранить в надёжном месте (1Password / зашифрованный backup / отдельный текстовый файл с правами 600).
