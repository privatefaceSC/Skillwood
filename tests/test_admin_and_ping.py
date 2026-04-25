import pytest

from data import db_sessions
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
def user_id(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x", tablet_ip="127.0.0.1")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def _login(client, uid):
    with client.session_transaction() as s:
        s['user_id'] = uid


def test_api_ping_is_public_and_returns_ok(client):
    response = client.get('/api/ping')
    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'service': 'skillwood'}


def test_admin_test_requires_login(client):
    response = client.get('/admin/test')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_admin_test_renders_form(client, user_id):
    _login(client, user_id)
    response = client.get('/admin/test')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    assert 'name="sender"' in body
    assert 'name="text"' in body
    assert 'name="messenger_name"' in body


def test_admin_test_post_records_message(client, user_id):
    _login(client, user_id)
    response = client.post('/admin/test', data={
        "messenger_name": "Telegram",
        "sender": "Иван",
        "text": "привет из тестера",
    })
    assert response.status_code == 200
    db = db_sessions.create_session()
    try:
        msgs = db.query(Messages).all()
        assert len(msgs) == 1
        assert msgs[0].text == "привет из тестера"
        assert msgs[0].handle_id is not None
    finally:
        db.close()


def test_admin_test_post_validates_fields(client, user_id):
    _login(client, user_id)
    response = client.post('/admin/test', data={
        "messenger_name": "", "sender": "X", "text": "Y",
    })
    assert response.status_code == 200
    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 0
    finally:
        db.close()
