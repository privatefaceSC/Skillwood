from datetime import datetime

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
def user_and_contact(app):
    db = db_sessions.create_session()
    u = User(name="Test", surname="User", sex="male", email="t@e.com",
             hashed_password="x")
    db.add(u)
    db.commit()
    contact = Contact(user_id=u.id, display_name="Иван")
    db.add(contact)
    db.commit()
    h = MessengerHandle(contact_id=contact.id, user_id=u.id,
                        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван")
    db.add(h)
    db.commit()
    db.add(Messages(sender="Иван", text="привет", messenger_name="Telegram",
                    time="10:00", user_id=u.id, handle_id=h.id, created_at=datetime.now()))
    db.commit()
    out = (u.id, contact.id)
    db.close()
    return out


def _login(client, user_id):
    with client.session_transaction() as s:
        s['user_id'] = user_id


def test_contacts_index_lists_user_contacts(client, user_and_contact):
    user_id, _ = user_and_contact
    _login(client, user_id)
    response = client.get('/contacts')
    assert response.status_code == 200
    assert "Иван".encode("utf-8") in response.data


def test_contact_detail_shows_messages(client, user_and_contact):
    user_id, contact_id = user_and_contact
    _login(client, user_id)
    response = client.get(f'/contacts/{contact_id}')
    assert response.status_code == 200
    assert "привет".encode("utf-8") in response.data


def test_contact_detail_404_for_other_user(client, app, user_and_contact):
    _, contact_id = user_and_contact
    db = db_sessions.create_session()
    other = User(name="Other", surname="U", sex="male",
                 email="o@e.com", hashed_password="x")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()
    _login(client, other_id)
    response = client.get(f'/contacts/{contact_id}')
    assert response.status_code == 404


def test_messages_redirects_to_contacts(client, user_and_contact):
    user_id, _ = user_and_contact
    _login(client, user_id)
    response = client.get('/messages')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/contacts')


def test_contacts_requires_login(client):
    response = client.get('/contacts')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
