from data.contacts import Contact, MergeSuggestion, MessengerHandle
from data.migrations import migrate_to_contacts_v1
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_migration_groups_legacy_messages_by_sender(db_session):
    user = _make_user(db_session)
    db_session.add_all([
        Messages(sender="Иван", text="1", messenger_name="Telegram", time="10:00", user_id=user.id),
        Messages(sender="Иван", text="2", messenger_name="Telegram", time="10:01", user_id=user.id),
        Messages(sender="Пётр", text="3", messenger_name="Max", time="10:02", user_id=user.id),
    ])
    db_session.commit()

    stats = migrate_to_contacts_v1(db_session)

    assert db_session.query(Contact).count() == 2
    assert db_session.query(MessengerHandle).count() == 2
    assert all(m.handle_id is not None for m in db_session.query(Messages).all())
    assert stats["contacts_created"] == 2
    assert stats["handles_created"] == 2
    assert stats["messages_linked"] == 3


def test_migration_is_idempotent(db_session):
    user = _make_user(db_session)
    db_session.add(Messages(sender="Иван", text="1", messenger_name="Telegram",
                            time="10:00", user_id=user.id))
    db_session.commit()

    migrate_to_contacts_v1(db_session)
    second = migrate_to_contacts_v1(db_session)

    assert db_session.query(Contact).count() == 1
    assert db_session.query(MessengerHandle).count() == 1
    assert second["contacts_created"] == 0
    assert second["handles_created"] == 0


def test_migration_does_not_create_suggestions(db_session):
    user = _make_user(db_session)
    db_session.add_all([
        Messages(sender="Иван", text="1", messenger_name="Telegram", time="10:00", user_id=user.id),
        Messages(sender="Иванn", text="2", messenger_name="Max", time="10:01", user_id=user.id),
    ])
    db_session.commit()

    migrate_to_contacts_v1(db_session)

    assert db_session.query(MergeSuggestion).count() == 0
