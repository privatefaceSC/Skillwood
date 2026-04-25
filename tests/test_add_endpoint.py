import pytest

from data import db_sessions
from data.contacts import Contact, MessengerHandle
from data.users import Messages, User


@pytest.fixture
def app():
    from main import create_app
    db_sessions._reset_for_tests()
    a = create_app(":memory:")
    yield a
    db_sessions._reset_for_tests()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_with_device(app):
    """Регистрирует пользователя и привязывает к нему IP 127.0.0.1."""
    db = db_sessions.create_session()
    u = User(name="Test", surname="User", sex="male",
             email="t@e.com", hashed_password="x", tablet_ip="127.0.0.1")
    db.add(u)
    db.commit()
    user_id = u.id
    db.close()
    return user_id


def test_add_creates_contact_and_handle_for_new_sender(client, user_with_device):
    response = client.post('/add', data={
        "sender": "Иван", "text": "привет", "messenger_name": "Telegram",
    })
    assert response.status_code == 200

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 1
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
        msg = db.query(Messages).first()
        assert msg.handle_id is not None
        assert msg.text == "привет"
    finally:
        db.close()


def test_add_reuses_handle_for_repeat_sender(client, user_with_device):
    client.post('/add', data={"sender": "Иван", "text": "1", "messenger_name": "Telegram"})
    client.post('/add', data={"sender": "Иван", "text": "2", "messenger_name": "Telegram"})

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 2
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
    finally:
        db.close()


def test_add_returns_400_for_missing_fields(client, user_with_device):
    response = client.post('/add', data={"sender": "Иван"})
    assert response.status_code == 400

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 0
    finally:
        db.close()


def test_add_silently_ignores_unknown_device(client):
    response = client.post('/add', data={
        "sender": "Иван", "text": "привет", "messenger_name": "Telegram",
    })
    assert response.status_code == 200

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 0
    finally:
        db.close()
