import datetime

import sqlalchemy

from .db_sessions import SqlAlchemyBase


class DebugDump(SqlAlchemyBase):
    """Сырой дамп Notification.extras с устройства — для диагностики."""
    __tablename__ = 'debug_dumps'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer,
                                sqlalchemy.ForeignKey("users.id"), nullable=False)
    package_name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    app_name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    dump = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime,
                                   default=datetime.datetime.now, nullable=False)
