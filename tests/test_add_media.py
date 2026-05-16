import io

import pytest

from data import db_sessions
from data.attachments import Attachment
from data.crypto import decrypt_bytes
from data.devices import Device, hash_token
from data.users import Messages, User


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
def user_and_device(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    token = "raw-token-xyz"
    d = Device(user_id=u.id, name="Pad", token_hash=hash_token(token))
    db.add(d)
    db.commit()
    out = (u.id, d.id, token)
    db.close()
    return out


def _post_media(client, token, payload=b"\xff\xd8\xff\x00photo-bytes",
                dedup="content://x/1", sender="Мама"):
    return client.post(
        '/add_media',
        headers={"Authorization": f"Bearer {token}"},
        data={
            "sender": sender,
            "messenger_name": "MAX",
            "kind": "image",
            "dedup_key": dedup,
            "file": (io.BytesIO(payload), "photo.jpg"),
        },
        content_type='multipart/form-data',
    )


def test_add_media_creates_message_and_encrypted_attachment(client, user_and_device):
    uid, _, token = user_and_device
    payload = b"\xff\xd8\xffMAX-photo-binary"
    r = _post_media(client, token, payload=payload)
    assert r.status_code == 200

    db = db_sessions.create_session()
    try:
        att = db.query(Attachment).one()
        assert att.user_id == uid
        assert att.kind == "image"
        assert att.size == len(payload)
        msg = db.get(Messages, att.message_id)
        assert msg is not None
        assert msg.text == "📷 Фото"
        # Файл на диске зашифрован, но decrypt_bytes возвращает оригинал.
        import os
        full = os.path.join(os.environ["SKILLWOOD_MEDIA_ROOT"], att.stored_path)
        with open(full, "rb") as f:
            stored = f.read()
        assert stored != payload  # на диске шифротекст
        assert decrypt_bytes(stored) == payload
    finally:
        db.close()


def test_add_media_sticker_kind_persisted(client, user_and_device):
    _, _, token = user_and_device
    r = client.post(
        '/add_media',
        headers={"Authorization": f"Bearer {token}"},
        data={
            "sender": "Мама", "messenger_name": "MAX", "kind": "sticker",
            "dedup_key": "content://ru.oneme.app/getSmile?smileId=42",
            "file": (io.BytesIO(b"webp-sticker"), "s.webp"),
        },
        content_type='multipart/form-data',
    )
    assert r.status_code == 200
    db = db_sessions.create_session()
    try:
        att = db.query(Attachment).one()
        assert att.kind == "sticker"
        assert db.get(Messages, att.message_id).text == "🩷 Стикер"
    finally:
        db.close()


def test_add_media_dedup_skips_second(client, user_and_device):
    _, _, token = user_and_device
    assert _post_media(client, token, dedup="dup-key").status_code == 200
    r2 = _post_media(client, token, dedup="dup-key")
    assert r2.status_code == 200
    db = db_sessions.create_session()
    try:
        assert db.query(Attachment).count() == 1
        assert db.query(Messages).count() == 1
    finally:
        db.close()


def test_add_media_without_bearer_401(client):
    r = client.post('/add_media', data={
        "sender": "X", "messenger_name": "MAX",
        "file": (io.BytesIO(b"x"), "p.jpg"),
    }, content_type='multipart/form-data')
    assert r.status_code == 401


def test_add_media_without_file_400(client, user_and_device):
    _, _, token = user_and_device
    r = client.post('/add_media',
                     headers={"Authorization": f"Bearer {token}"},
                     data={"sender": "X", "messenger_name": "MAX"})
    assert r.status_code == 400


def test_attachment_get_requires_session(client, user_and_device):
    _, _, token = user_and_device
    _post_media(client, token)
    db = db_sessions.create_session()
    aid = db.query(Attachment).one().id
    db.close()
    assert client.get(f'/attachments/{aid}').status_code == 401


def test_attachment_get_returns_decrypted_image(client, user_and_device):
    uid, _, token = user_and_device
    payload = b"\x89PNG\r\n\x1a\nreal-bytes-here"
    _post_media(client, token, payload=payload)
    db = db_sessions.create_session()
    aid = db.query(Attachment).one().id
    db.close()

    with client.session_transaction() as sess:
        sess['user_id'] = uid
    r = client.get(f'/attachments/{aid}')
    assert r.status_code == 200
    assert r.data == payload


def test_attachment_get_foreign_user_404(client, user_and_device):
    _, _, token = user_and_device
    _post_media(client, token)
    db = db_sessions.create_session()
    aid = db.query(Attachment).one().id
    other = User(name="O", surname="O", sex="male",
                 email="o@e.com", hashed_password="x")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()

    with client.session_transaction() as sess:
        sess['user_id'] = other_id
    assert client.get(f'/attachments/{aid}').status_code == 404
