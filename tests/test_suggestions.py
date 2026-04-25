from data.contacts import Contact, MergeSuggestion, MessengerHandle
from data.matching import suggest_merges_for_handle
from data.users import User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _make_handle(db, user, display_name, messenger_name, sender_raw, sender_normalized):
    contact = Contact(user_id=user.id, display_name=display_name)
    db.add(contact)
    db.commit()
    h = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name=messenger_name, sender_raw=sender_raw,
        sender_normalized=sender_normalized,
    )
    db.add(h)
    db.commit()
    return h


def test_creates_suggestion_for_similar_name(db_session):
    user = _make_user(db_session)
    existing = _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Иванn", "Max", "Иванn", "иванn")

    suggest_merges_for_handle(db_session, new)

    sugs = db_session.query(MergeSuggestion).all()
    assert len(sugs) == 1
    assert sugs[0].source_handle_id == new.id
    assert sugs[0].target_contact_id == existing.contact_id
    assert sugs[0].status == "pending"
    assert sugs[0].score >= 0.7


def test_no_suggestion_for_dissimilar_name(db_session):
    user = _make_user(db_session)
    _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Пётр", "Max", "Пётр", "пётр")

    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_suggestion_against_own_contact(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    h1 = MessengerHandle(contact_id=contact.id, user_id=user.id,
                         messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван")
    h2 = MessengerHandle(contact_id=contact.id, user_id=user.id,
                         messenger_name="Max", sender_raw="Иванn", sender_normalized="иванn")
    db_session.add_all([h1, h2])
    db_session.commit()

    suggest_merges_for_handle(db_session, h2)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_suggestion_across_users(db_session):
    user_a = _make_user(db_session, "a@example.com")
    user_b = _make_user(db_session, "b@example.com")
    _make_handle(db_session, user_a, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user_b, "Иван", "Max", "Иван", "иван")

    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_duplicate_suggestion(db_session):
    user = _make_user(db_session)
    _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Иванn", "Max", "Иванn", "иванn")

    suggest_merges_for_handle(db_session, new)
    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 1
