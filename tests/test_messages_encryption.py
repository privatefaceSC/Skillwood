import sqlalchemy

from data import db_sessions
from data.contacts import record_message
from data.crypto import _PREFIX
from data.migrations import migrate_encrypt_messages_v1
from data.users import Messages, User


def _make_user(db, email="u@e.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u); db.commit()
    return u


def test_record_message_stores_ciphertext_in_db(db_session):
    user = _make_user(db_session)
    record_message(db_session, user.id, "Telegram", "Иван", "секретный текст")

    # Через raw SQL обходим TypeDecorator → видим именно то, что лежит на диске.
    raw_text = db_session.execute(
        sqlalchemy.text("SELECT text FROM messages WHERE user_id = :u"),
        {"u": user.id},
    ).scalar()
    assert raw_text.startswith(_PREFIX)
    assert "секретный текст" not in raw_text


def test_orm_read_returns_plaintext(db_session):
    """TypeDecorator должен быть прозрачным для прикладного кода."""
    user = _make_user(db_session)
    record_message(db_session, user.id, "Telegram", "Иван", "секретный текст")
    msg = db_session.query(Messages).first()
    assert msg.text == "секретный текст"


def test_long_unicode_message_roundtrip(db_session):
    user = _make_user(db_session)
    text = "🚀 " + ("длинное сообщение с эмодзи " * 50)
    record_message(db_session, user.id, "Telegram", "Иван", text)
    msg = db_session.query(Messages).first()
    assert msg.text == text


def test_migrate_encrypts_legacy_plaintext_via_raw_insert(db_session):
    """Сценарий миграции боевой БД: в таблице уже лежат plaintext-сообщения
    (созданные до релиза шифрования). После прогона миграции они зашифрованы."""
    user = _make_user(db_session)
    # Вставляем напрямую через raw SQL — обходим TypeDecorator, имитируем
    # «старые» сообщения, попавшие в БД до релиза шифрования.
    db_session.execute(
        sqlalchemy.text(
            "INSERT INTO messages (sender, text, messenger_name, time, user_id) "
            "VALUES (:s, :t, :m, :ti, :u)"
        ),
        [
            {"s": "Иван", "t": "первое", "m": "Telegram", "ti": "10:00", "u": user.id},
            {"s": "Иван", "t": "второе", "m": "Telegram", "ti": "10:01", "u": user.id},
            {"s": "Пётр", "t": "третье", "m": "Max", "ti": "10:02", "u": user.id},
        ],
    )
    db_session.commit()

    stats = migrate_encrypt_messages_v1(db_session)
    assert stats == {"encrypted": 3}

    raw_texts = [
        r[0] for r in
        db_session.execute(sqlalchemy.text("SELECT text FROM messages ORDER BY id")).fetchall()
    ]
    for t in raw_texts:
        assert t.startswith(_PREFIX), t

    # И через ORM прикладной код видит исходный plaintext.
    msgs = db_session.query(Messages).order_by(Messages.id).all()
    assert [m.text for m in msgs] == ["первое", "второе", "третье"]


def test_migrate_is_idempotent(db_session):
    user = _make_user(db_session)
    db_session.execute(
        sqlalchemy.text(
            "INSERT INTO messages (sender, text, messenger_name, time, user_id) "
            "VALUES (:s, :t, :m, :ti, :u)"
        ),
        {"s": "Иван", "t": "первое", "m": "Telegram", "ti": "10:00", "u": user.id},
    )
    db_session.commit()
    first = migrate_encrypt_messages_v1(db_session)
    second = migrate_encrypt_messages_v1(db_session)
    assert first == {"encrypted": 1}
    assert second == {"encrypted": 0}


def test_migrate_skips_already_encrypted_messages(db_session):
    user = _make_user(db_session)
    # Сообщение, записанное через ORM (уже зашифровано).
    record_message(db_session, user.id, "Telegram", "Иван", "уже шифр")
    stats = migrate_encrypt_messages_v1(db_session)
    assert stats == {"encrypted": 0}


def test_orm_reads_legacy_plaintext_before_migration(db_session):
    """Сценарий «выкатили код, миграцию ещё не запускали»: старые сообщения
    в БД лежат как plaintext, ORM должен их читать как есть."""
    user = _make_user(db_session)
    db_session.execute(
        sqlalchemy.text(
            "INSERT INTO messages (sender, text, messenger_name, time, user_id) "
            "VALUES (:s, :t, :m, :ti, :u)"
        ),
        {"s": "Иван", "t": "legacy plaintext", "m": "Telegram", "ti": "10:00", "u": user.id},
    )
    db_session.commit()
    msg = db_session.query(Messages).first()
    assert msg.text == "legacy plaintext"
