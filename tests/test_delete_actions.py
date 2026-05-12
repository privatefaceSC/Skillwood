from datetime import datetime

import pytest

from data import db_sessions
from data.contacts import Contact, MergeSuggestion, MessengerHandle, record_message
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


def _make_user(db, email="u@e.com", ip="127.0.0.1"):
    u = User(name="U", surname="S", sex="male", email=email,
            hashed_password="x", tablet_ip=ip)
    db.add(u); db.commit()
    return u


def _login(client, user_id):
    with client.session_transaction() as s:
        s['user_id'] = user_id


# ---------- /contacts/<id>/delete ----------


def test_contact_delete_removes_contact_handles_messages(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    record_message(db, u.id, "Telegram", "Иван", "привет")
    record_message(db, u.id, "Telegram", "Иван", "ещё одно")
    contact = db.query(Contact).first()
    user_id, contact_id = u.id, contact.id
    db.close()

    _login(client, user_id)
    resp = client.post(f"/contacts/{contact_id}/delete")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    db = db_sessions.create_session()
    assert db.get(Contact, contact_id) is None
    assert db.query(MessengerHandle).filter(MessengerHandle.contact_id == contact_id).count() == 0
    assert db.query(Messages).filter(Messages.user_id == user_id).count() == 0
    db.close()


def test_contact_delete_404_for_other_user(client):
    db = db_sessions.create_session()
    owner = _make_user(db, email="o@e.com", ip="127.0.0.1")
    record_message(db, owner.id, "Telegram", "Иван", "привет")
    contact = db.query(Contact).first()
    intruder = _make_user(db, email="x@e.com", ip="127.0.0.2")
    contact_id, intruder_id = contact.id, intruder.id
    db.close()

    _login(client, intruder_id)
    resp = client.post(f"/contacts/{contact_id}/delete")
    assert resp.status_code == 404
    db = db_sessions.create_session()
    assert db.get(Contact, contact_id) is not None  # не удалили
    db.close()


def test_contact_delete_requires_login(client):
    resp = client.post("/contacts/1/delete")
    assert resp.status_code == 401


def test_contact_delete_404_for_unknown_id(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    user_id = u.id
    db.close()
    _login(client, user_id)
    resp = client.post("/contacts/9999/delete")
    assert resp.status_code == 404


def test_contact_delete_cleans_up_merge_suggestions(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    # создаём два handle, похожих по имени — это породит MergeSuggestion
    record_message(db, u.id, "Telegram", "Иван", "1")
    record_message(db, u.id, "Telegram", "Иванn", "2")
    assert db.query(MergeSuggestion).count() >= 1

    # удаляем первый contact — должны исчезнуть suggestion'ы, связанные с ним
    first_contact = db.query(Contact).order_by(Contact.id.asc()).first()
    contact_id, user_id = first_contact.id, u.id
    db.close()

    _login(client, user_id)
    resp = client.post(f"/contacts/{contact_id}/delete")
    assert resp.status_code == 200

    db = db_sessions.create_session()
    # suggestion'ы с participated handles удалённого контакта пропали
    surviving = db.query(MergeSuggestion).all()
    for s in surviving:
        h = db.get(MessengerHandle, s.source_handle_id)
        assert h is not None and h.contact_id != contact_id
        assert s.target_contact_id != contact_id
    db.close()


# ---------- /messages/<id>/delete ----------


def test_message_delete_removes_one_message(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    m1 = record_message(db, u.id, "Telegram", "Иван", "первое")
    m2 = record_message(db, u.id, "Telegram", "Иван", "второе")
    user_id, m1_id, m2_id = u.id, m1.id, m2.id
    db.close()

    _login(client, user_id)
    resp = client.post(f"/messages/{m1_id}/delete")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    db = db_sessions.create_session()
    assert db.get(Messages, m1_id) is None
    assert db.get(Messages, m2_id) is not None  # второе осталось
    db.close()


def test_message_delete_404_for_other_user(client):
    db = db_sessions.create_session()
    owner = _make_user(db, email="o@e.com", ip="127.0.0.1")
    msg = record_message(db, owner.id, "Telegram", "Иван", "секрет")
    intruder = _make_user(db, email="x@e.com", ip="127.0.0.2")
    msg_id, intruder_id = msg.id, intruder.id
    db.close()

    _login(client, intruder_id)
    resp = client.post(f"/messages/{msg_id}/delete")
    assert resp.status_code == 404
    db = db_sessions.create_session()
    assert db.get(Messages, msg_id) is not None
    db.close()


def test_message_delete_requires_login(client):
    resp = client.post("/messages/1/delete")
    assert resp.status_code == 401


def test_message_delete_404_for_unknown_id(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    user_id = u.id
    db.close()
    _login(client, user_id)
    resp = client.post("/messages/9999/delete")
    assert resp.status_code == 404


# ---------- /contacts/<id>/rename: XHR ветка возвращает JSON ----------


def test_contact_rename_xhr_returns_json(client):
    db = db_sessions.create_session()
    u = _make_user(db)
    record_message(db, u.id, "Telegram", "Иван", "привет")
    contact = db.query(Contact).first()
    user_id, contact_id = u.id, contact.id
    db.close()

    _login(client, user_id)
    resp = client.post(
        f"/contacts/{contact_id}/rename",
        data={"display_name": "Иван Иванович"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "display_name": "Иван Иванович"}

    db = db_sessions.create_session()
    assert db.get(Contact, contact_id).display_name == "Иван Иванович"
    db.close()


def test_contact_rename_plain_form_still_redirects(client):
    """Старый сценарий с /contacts/manage не сломан."""
    db = db_sessions.create_session()
    u = _make_user(db)
    record_message(db, u.id, "Telegram", "Иван", "привет")
    contact = db.query(Contact).first()
    user_id, contact_id = u.id, contact.id
    db.close()

    _login(client, user_id)
    resp = client.post(
        f"/contacts/{contact_id}/rename",
        data={"display_name": "Новое имя"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/contacts/manage")
