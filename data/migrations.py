"""Одноразовые миграции данных.

Запуск: `python -m data.migrations`.
"""
from datetime import datetime

from . import db_sessions
from .contacts import Contact, MessengerHandle
from .matching import normalize
from .users import Messages


def migrate_to_contacts_v1(db) -> dict:
    """Привязать существующие Messages к Contact + MessengerHandle.

    Идемпотентна: повторный вызов не создаёт дубликатов и не трогает уже
    привязанные сообщения. Не запускает автомэтчинг.

    Возвращает {"contacts_created", "handles_created", "messages_linked"}.
    """
    contacts_created = 0
    handles_created = 0
    messages_linked = 0

    triples = (
        db.query(Messages.user_id, Messages.messenger_name, Messages.sender)
        .filter(Messages.handle_id.is_(None))
        .distinct()
        .all()
    )

    for user_id, messenger_name, sender in triples:
        if user_id is None or sender is None or messenger_name is None:
            continue

        handle = (
            db.query(MessengerHandle)
            .filter(
                MessengerHandle.user_id == user_id,
                MessengerHandle.messenger_name == messenger_name,
                MessengerHandle.sender_raw == sender,
            )
            .first()
        )
        if handle is None:
            contact = Contact(user_id=user_id, display_name=sender)
            db.add(contact)
            db.flush()
            contacts_created += 1
            handle = MessengerHandle(
                contact_id=contact.id,
                user_id=user_id,
                messenger_name=messenger_name,
                sender_raw=sender,
                sender_normalized=normalize(sender),
            )
            db.add(handle)
            db.flush()
            handles_created += 1

        updated = (
            db.query(Messages)
            .filter(
                Messages.handle_id.is_(None),
                Messages.user_id == user_id,
                Messages.messenger_name == messenger_name,
                Messages.sender == sender,
            )
            .update({
                Messages.handle_id: handle.id,
                Messages.created_at: datetime.now(),
            }, synchronize_session=False)
        )
        messages_linked += updated

    db.commit()
    return {
        "contacts_created": contacts_created,
        "handles_created": handles_created,
        "messages_linked": messages_linked,
    }


if __name__ == "__main__":
    db_sessions.global_init("db/blogs.db")
    session = db_sessions.create_session()
    try:
        stats = migrate_to_contacts_v1(session)
        print(f"Миграция завершена: {stats}")
    finally:
        session.close()
