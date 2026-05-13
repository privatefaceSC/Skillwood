from data.contacts import (
    Contact,
    MessengerHandle,
    find_or_create_handle,
    record_message,
)
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email,
             hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_find_or_create_handle_new_creates_contact_and_handle(db_session):
    user = _make_user(db_session)
    handle, created = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    assert created is True
    assert handle.id is not None
    assert handle.sender_raw == "Иван"
    assert handle.sender_normalized == "иван"
    contact = db_session.get(Contact, handle.contact_id)
    assert contact.display_name == "Иван"


def test_find_or_create_handle_existing_returns_same(db_session):
    user = _make_user(db_session)
    h1, c1 = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    h2, c2 = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    assert c1 is True and c2 is False
    assert h1.id == h2.id
    assert db_session.query(Contact).count() == 1


def test_record_message_links_to_handle(db_session):
    user = _make_user(db_session)
    msg = record_message(db_session, user.id, "Telegram", "Иван", "привет")
    assert msg.id is not None
    assert msg.handle_id is not None
    assert msg.user_id == user.id
    assert msg.text == "привет"
    handle = db_session.get(MessengerHandle, msg.handle_id)
    assert handle.sender_raw == "Иван"


def test_record_message_reuses_handle_for_same_sender(db_session):
    user = _make_user(db_session)
    m1 = record_message(db_session, user.id, "Telegram", "Иван", "привет")
    m2 = record_message(db_session, user.id, "Telegram", "Иван", "ещё одно")
    assert m1.handle_id == m2.handle_id
    assert db_session.query(Contact).count() == 1
    assert db_session.query(MessengerHandle).count() == 1
    assert db_session.query(Messages).count() == 2
