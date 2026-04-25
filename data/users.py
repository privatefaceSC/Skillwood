import datetime
import sqlalchemy
from sqlalchemy import orm
from .db_sessions import SqlAlchemyBase
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin
from sqlalchemy_serializer import SerializerMixin



class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    surname = sqlalchemy.Column(sqlalchemy.String)
    name = sqlalchemy.Column(sqlalchemy.String)
    sex = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    email = sqlalchemy.Column(sqlalchemy.String, unique=True)
    hashed_password = sqlalchemy.Column(sqlalchemy.String)
    modified_date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now)
    tablet_ip = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    connect_code = sqlalchemy.Column(sqlalchemy.String, nullable=True, unique=True)

class Messages(SqlAlchemyBase):
    __tablename__ = 'messages'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    sender = sqlalchemy.Column(sqlalchemy.String)
    text = sqlalchemy.Column(sqlalchemy.String)
    messenger_name = sqlalchemy.Column(sqlalchemy.String)
    time = sqlalchemy.Column(sqlalchemy.String)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=True)
    # chats_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("chats.id"), nullable=True)

# class Chats(SqlAlchemyBase):
#     __tablename__ = 'chats'
#     id = sqlalchemy.Column(sqlalchemy.Integer,
#                            primary_key=True, autoincrement=True)
#     name = sqlalchemy.Column(sqlalchemy.String)
#     text = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("messages.text"), nullable=True)
#     messenger_name = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("messages.messenger_name"), nullable=True)
#     time = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("messages.time"), nullable=True)


