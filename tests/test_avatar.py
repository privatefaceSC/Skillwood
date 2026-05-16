import io
import os

import pytest

from data import db_sessions
from data.crypto import decrypt_bytes
from data.users import User


@pytest.fixture
def app(tmp_path, monkeypatch):
    from main import create_app
    monkeypatch.setenv("SKILLWOOD_MEDIA_ROOT", str(tmp_path / "media"))
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
    u = User(name="Иван", surname="U", sex="male",
             email="i@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def _login(client, uid):
    with client.session_transaction() as sess:
        sess['user_id'] = uid


def _upload(client, payload=b"\x89PNG\r\n\x1a\navatar-bytes",
            filename="ava.png", ctype="image/png"):
    return client.post(
        '/home/avatar',
        data={"avatar": (io.BytesIO(payload), filename, ctype)},
        content_type='multipart/form-data',
    )


def test_avatar_get_requires_session(client):
    assert client.get('/home/avatar').status_code == 401


def test_avatar_post_requires_session(client):
    r = client.post('/home/avatar')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_avatar_get_404_when_none(client, user_id):
    _login(client, user_id)
    assert client.get('/home/avatar').status_code == 404


def test_avatar_upload_then_served_decrypted(client, user_id):
    _login(client, user_id)
    payload = b"\x89PNG\r\n\x1a\nreal-avatar-binary"
    r = _upload(client, payload=payload, ctype="image/png")
    assert r.status_code == 302
    assert '/home' in r.headers['Location']

    g = client.get('/home/avatar')
    assert g.status_code == 200
    assert g.data == payload
    assert g.mimetype == "image/png"

    # На диске — шифротекст, decrypt_bytes возвращает оригинал.
    enc = os.path.join(os.environ["SKILLWOOD_MEDIA_ROOT"],
                       str(user_id), "avatar.enc")
    with open(enc, "rb") as f:
        stored = f.read()
    assert stored != payload
    assert decrypt_bytes(stored) == payload


def test_avatar_rejects_non_image(client, user_id):
    _login(client, user_id)
    r = client.post(
        '/home/avatar',
        data={"avatar": (io.BytesIO(b"%PDF-1.4 not an image"),
                         "doc.pdf", "application/pdf")},
        content_type='multipart/form-data',
    )
    assert r.status_code == 302
    # Ничего не сохранилось — аватарки по-прежнему нет.
    assert client.get('/home/avatar').status_code == 404


def test_home_shows_avatar_after_upload(client, user_id):
    _login(client, user_id)
    # Форма всегда шлёт на /home/avatar (action), поэтому различаем по
    # тегу <img src="/home/avatar"> — он появляется только при наличии аватарки.
    before = client.get('/home')
    assert b'src="/home/avatar"' not in before.data  # пока плейсхолдер-инициал

    _upload(client)
    after = client.get('/home')
    assert b'src="/home/avatar"' in after.data        # теперь картинка
