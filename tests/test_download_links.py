import pytest

from data import db_sessions
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


def _make_user(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x", connect_code="12345678")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_home_has_download_link(client, app):
    uid = _make_user(app)
    with client.session_transaction() as s:
        s['user_id'] = uid
    r = client.get('/home')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert '/download' in body


def test_code_has_download_link(client, app):
    uid = _make_user(app)
    with client.session_transaction() as s:
        s['user_id'] = uid
    r = client.get('/code')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert '/download' in body
