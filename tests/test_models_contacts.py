import pytest
from sqlalchemy.exc import IntegrityError

from data.contacts import Contact, MergeSuggestion, MessengerHandle
from data.users import User


def _make_user(db, email="u@example.com"):
    user = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def test_create_contact(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    assert contact.id is not None
    assert contact.created_at is not None


def test_create_messenger_handle(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    handle = MessengerHandle(
        contact_id=contact.id,
        user_id=user.id,
        messenger_name="Telegram",
        sender_raw="Иван",
        sender_normalized="иван",
    )
    db_session.add(handle)
    db_session.commit()
    assert handle.id is not None


def test_messenger_handle_unique_constraint(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    h1 = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(h1)
    db_session.commit()
    h2 = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(h2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_merge_suggestion(db_session):
    user = _make_user(db_session)
    c1 = Contact(user_id=user.id, display_name="A")
    c2 = Contact(user_id=user.id, display_name="B")
    db_session.add_all([c1, c2])
    db_session.commit()
    h = MessengerHandle(
        contact_id=c1.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="A", sender_normalized="a",
    )
    db_session.add(h)
    db_session.commit()
    sug = MergeSuggestion(
        user_id=user.id,
        source_handle_id=h.id,
        target_contact_id=c2.id,
        score=0.9,
        status="pending",
    )
    db_session.add(sug)
    db_session.commit()
    assert sug.id is not None


def test_merge_suggestion_unique_constraint(db_session):
    user = _make_user(db_session)
    c1 = Contact(user_id=user.id, display_name="A")
    c2 = Contact(user_id=user.id, display_name="B")
    db_session.add_all([c1, c2])
    db_session.commit()
    h = MessengerHandle(
        contact_id=c1.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="A", sender_normalized="a",
    )
    db_session.add(h)
    db_session.commit()
    s1 = MergeSuggestion(user_id=user.id, source_handle_id=h.id,
                        target_contact_id=c2.id, score=0.9, status="pending")
    db_session.add(s1)
    db_session.commit()
    s2 = MergeSuggestion(user_id=user.id, source_handle_id=h.id,
                        target_contact_id=c2.id, score=0.95, status="pending")
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()
