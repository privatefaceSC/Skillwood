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
def user_and_token(app):
    db = db_sessions.create_session()
    u = User(name="Test", surname="U", sex="male",
             email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    raw_token = "test-token-1234567890abcdef"
    d = Device(user_id=u.id, name="Pad", token_hash=hash_token(raw_token))
    db.add(d)
    db.commit()
    out = (u.id, raw_token)
    db.close()
    return out


def test_me_returns_user_info_with_valid_token(client, user_and_token):
    _, token = user_and_token
    r = client.get('/api/me', headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["user"]["name"] == "Test"
    assert data["device"]["name"] == "Pad"


def test_me_returns_401_without_header(client):
    r = client.get('/api/me')
    assert r.status_code == 401


def test_me_returns_401_with_invalid_token(client, user_and_token):
    r = client.get('/api/me', headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 401


def test_me_returns_401_with_malformed_header(client, user_and_token):
    _, token = user_and_token
    r = client.get('/api/me', headers={"Authorization": token})  # без Bearer
    assert r.status_code == 401
