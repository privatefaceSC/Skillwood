import pytest

from data import db_sessions
from data.devices import Device, hash_token
from data.users import User


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
def user_with_code(app):
    db = db_sessions.create_session()
    u = User(name="Test", surname="User", sex="male",
             email="t@e.com", hashed_password="x", connect_code="12345678")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_api_connect_creates_device(client, user_with_code):
    r = client.post('/api/connect', json={
        "code": "12345678", "device_name": "Xiaomi Pad",
    })
    assert r.status_code == 200
    data = r.get_json()
    assert "token" in data
    assert len(data["token"]) >= 40
    assert data["user"]["name"] == "Test"
    assert data["device"]["name"] == "Xiaomi Pad"

    db = db_sessions.create_session()
    try:
        devices = db.query(Device).all()
        assert len(devices) == 1
        assert devices[0].user_id == user_with_code
        assert devices[0].name == "Xiaomi Pad"
        assert devices[0].token_hash == hash_token(data["token"])
    finally:
        db.close()


def test_api_connect_rejects_unknown_code(client):
    r = client.post('/api/connect', json={"code": "99999999", "device_name": "X"})
    assert r.status_code == 404


def test_api_connect_rejects_empty_code(client):
    r = client.post('/api/connect', json={"code": "", "device_name": "X"})
    assert r.status_code == 400


def test_api_connect_rejects_empty_device_name(client, user_with_code):
    r = client.post('/api/connect', json={"code": "12345678", "device_name": ""})
    assert r.status_code == 400


def test_api_connect_creates_distinct_tokens_for_two_devices(client, user_with_code):
    r1 = client.post('/api/connect', json={"code": "12345678", "device_name": "A"})
    r2 = client.post('/api/connect', json={"code": "12345678", "device_name": "B"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["token"] != r2.get_json()["token"]
