import re
from datetime import datetime, timedelta

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


def _login(client, user_id):
    with client.session_transaction() as s:
        s['user_id'] = user_id


@pytest.fixture
def user_with_chat(app):
    """Пользователь с одним контактом и тремя сообщениями: два «старых», одно «новое»."""
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x")
    db.add(u)
    db.commit()
    c = Contact(user_id=u.id, display_name="Иван")
    db.add(c)
    db.commit()
    h = MessengerHandle(contact_id=c.id, user_id=u.id,
                        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван")
    db.add(h)
    db.commit()

    base = datetime(2026, 4, 25, 10, 0, 0)
    db.add_all([
        Messages(sender="Иван", text="старое 1", messenger_name="Telegram", time="10:00",
                 user_id=u.id, handle_id=h.id, created_at=base),
        Messages(sender="Иван", text="старое 2", messenger_name="Telegram", time="10:01",
                 user_id=u.id, handle_id=h.id, created_at=base + timedelta(minutes=1)),
        Messages(sender="Иван", text="свежак", messenger_name="Telegram", time="10:02",
                 user_id=u.id, handle_id=h.id, created_at=base + timedelta(minutes=2)),
    ])
    # Устанавливаем last_read_at между «старыми» и «свежим» — должно быть 1 непрочитанное.
    c.last_read_at = base + timedelta(minutes=1, seconds=30)
    db.commit()
    out = (u.id, c.id, h.id)
    db.close()
    return out


def test_contacts_index_shows_unread_count(client, user_with_chat):
    user_id, contact_id, _ = user_with_chat
    _login(client, user_id)
    response = client.get('/contacts')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    # В шаблоне бейдж рисуется как `<span class="badge-unread">N</span>`.
    assert 'badge-unread">1<' in body


def test_contact_detail_messages_in_ascending_order(client, user_with_chat):
    user_id, contact_id, _ = user_with_chat
    _login(client, user_id)
    response = client.get(f'/contacts/{contact_id}')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    # Ищем именно бабблы (<div class="text">…</div>) — preview в левом списке
    # тоже содержит «свежак», но без этой обёртки.
    pos_old1 = body.find('<div class="text">старое 1</div>')
    pos_old2 = body.find('<div class="text">старое 2</div>')
    pos_new = body.find('<div class="text">свежак</div>')
    assert pos_old1 != -1 and pos_old2 != -1 and pos_new != -1
    assert pos_old1 < pos_old2 < pos_new


def test_opening_chat_resets_unread(client, user_with_chat):
    user_id, contact_id, _ = user_with_chat
    _login(client, user_id)

    # Сначала проверяем, что есть непрочитанное.
    body = client.get('/contacts').data.decode('utf-8')
    assert 'badge-unread">1<' in body

    # Открываем чат.
    client.get(f'/contacts/{contact_id}')

    # Возвращаемся к списку — отрендеренного бейджа с числом быть не должно.
    # (В HTML могут встречаться вхождения «badge-unread» внутри JS-шаблона
    # для polling — нас интересует только реально отрисованный DOM-бейдж.)
    body = client.get('/contacts').data.decode('utf-8')
    assert re.search(r'<span class="badge-unread">\s*\d', body) is None


def test_messages_json_returns_ascending_order(client, user_with_chat):
    user_id, contact_id, _ = user_with_chat
    _login(client, user_id)
    response = client.get(f'/contacts/{contact_id}/messages.json')
    assert response.status_code == 200
    texts = [m['text'] for m in response.get_json()['messages']]
    assert texts == ["старое 1", "старое 2", "свежак"]
