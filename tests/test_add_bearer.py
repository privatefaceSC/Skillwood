from datetime import datetime

import pytest

from data import db_sessions
from data.contacts import Contact, MessengerHandle
from data.devices import Device, hash_token
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
def user_and_device(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x")
    db.add(u)
    db.commit()
    raw_token = "raw-token-xyz"
    d = Device(user_id=u.id, name="Pad", token_hash=hash_token(raw_token))
    db.add(d)
    db.commit()
    out = (u.id, d.id, raw_token)
    db.close()
    return out


def test_add_with_bearer_records_message(client, user_and_device):
    _, _, token = user_and_device
    r = client.post('/add',
                    headers={"Authorization": f"Bearer {token}"},
                    data={"sender": "Иван", "text": "привет",
                          "messenger_name": "Telegram"})
    assert r.status_code == 200
    db = db_sessions.create_session()
    try:
        msgs = db.query(Messages).all()
        assert len(msgs) == 1
        assert msgs[0].text == "привет"
        assert msgs[0].handle_id is not None
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
    finally:
        db.close()


def test_add_with_invalid_bearer_returns_401(client):
    r = client.post('/add',
                    headers={"Authorization": "Bearer not-a-real-token"},
                    data={"sender": "X", "text": "Y", "messenger_name": "Z"})
    assert r.status_code == 401


def test_add_without_bearer_returns_401(client):
    r = client.post('/add', data={"sender": "X", "text": "Y", "messenger_name": "Z"})
    assert r.status_code == 401


def test_add_with_bearer_updates_device_last_seen(client, user_and_device):
    _, device_id, token = user_and_device
    client.post('/add',
                headers={"Authorization": f"Bearer {token}"},
                data={"sender": "Иван", "text": "привет",
                      "messenger_name": "Telegram"})
    db = db_sessions.create_session()
    try:
        d = db.get(Device, device_id)
        assert d.last_seen_ip is not None
        assert d.last_seen_at is not None
    finally:
        db.close()
