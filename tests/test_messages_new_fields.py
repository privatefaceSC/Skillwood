from datetime import datetime

from data.contacts import Contact, MessengerHandle
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_message_has_handle_id_and_created_at(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    handle = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(handle)
    db_session.commit()

    now = datetime.now()
    msg = Messages(
        sender="Иван", text="привет", messenger_name="Telegram",
        time=now.strftime("%H:%M"), user_id=user.id,
        handle_id=handle.id, created_at=now,
    )
    db_session.add(msg)
    db_session.commit()
    assert msg.id is not None
    assert msg.handle_id == handle.id
    assert msg.created_at == now


def test_message_handle_id_can_be_null_for_legacy(db_session):
    user = _make_user(db_session)
    msg = Messages(
        sender="Иван", text="привет", messenger_name="Telegram",
        time="10:00", user_id=user.id,
    )
    db_session.add(msg)
    db_session.commit()
    assert msg.id is not None
    assert msg.handle_id is None
