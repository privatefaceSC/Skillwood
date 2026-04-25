import datetime

import sqlalchemy
from sqlalchemy import orm

from .db_sessions import SqlAlchemyBase


class Contact(SqlAlchemyBase):
    __tablename__ = 'contacts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    display_name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)

    handles = orm.relationship("MessengerHandle", back_populates="contact",
                               foreign_keys="MessengerHandle.contact_id")


class MessengerHandle(SqlAlchemyBase):
    __tablename__ = 'messenger_handles'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    contact_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contacts.id"), nullable=False)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    messenger_name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    sender_raw = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    sender_normalized = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('user_id', 'messenger_name', 'sender_raw',
                                    name='uq_handle_user_messenger_sender'),
    )

    contact = orm.relationship("Contact", back_populates="handles", foreign_keys=[contact_id])


class MergeSuggestion(SqlAlchemyBase):
    __tablename__ = 'merge_suggestions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    source_handle_id = sqlalchemy.Column(sqlalchemy.Integer,
                                         sqlalchemy.ForeignKey("messenger_handles.id"), nullable=False)
    target_contact_id = sqlalchemy.Column(sqlalchemy.Integer,
                                          sqlalchemy.ForeignKey("contacts.id"), nullable=False)
    score = sqlalchemy.Column(sqlalchemy.Float, nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String, nullable=False, default="pending")
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('source_handle_id', 'target_contact_id',
                                    name='uq_suggestion_handle_contact'),
    )

    source_handle = orm.relationship("MessengerHandle", foreign_keys=[source_handle_id])
    target_contact = orm.relationship("Contact", foreign_keys=[target_contact_id])


def find_or_create_handle(db, user_id: int, messenger_name: str, sender_raw: str):
    """Возвращает (MessengerHandle, created: bool).

    Если handle для (user_id, messenger_name, sender_raw) уже есть — отдаём его.
    Иначе создаём Contact с display_name=sender_raw и MessengerHandle, запускаем
    suggest_merges_for_handle и возвращаем созданный handle с created=True.
    """
    from .matching import normalize, suggest_merges_for_handle

    handle = (
        db.query(MessengerHandle)
        .filter(
            MessengerHandle.user_id == user_id,
            MessengerHandle.messenger_name == messenger_name,
            MessengerHandle.sender_raw == sender_raw,
        )
        .first()
    )
    if handle:
        return handle, False

    contact = Contact(user_id=user_id, display_name=sender_raw)
    db.add(contact)
    db.flush()
    handle = MessengerHandle(
        contact_id=contact.id,
        user_id=user_id,
        messenger_name=messenger_name,
        sender_raw=sender_raw,
        sender_normalized=normalize(sender_raw),
    )
    db.add(handle)
    db.flush()
    suggest_merges_for_handle(db, handle)
    return handle, True


def record_message(db, user_id: int, messenger_name: str, sender_raw: str, text: str):
    """Сохранить сообщение, найдя/создав соответствующий handle."""
    import datetime as _dt

    from .users import Messages

    handle, _ = find_or_create_handle(db, user_id, messenger_name, sender_raw)
    now = _dt.datetime.now()
    msg = Messages(
        sender=sender_raw,
        text=text,
        messenger_name=messenger_name,
        time=now.strftime("%H:%M"),
        user_id=user_id,
        handle_id=handle.id,
        created_at=now,
    )
    db.add(msg)
    db.commit()
    return msg
