import datetime

import sqlalchemy

from .db_sessions import SqlAlchemyBase


class Contact(SqlAlchemyBase):
    __tablename__ = 'contacts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    display_name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)


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
