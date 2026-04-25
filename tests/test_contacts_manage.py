import pytest

from data import db_sessions
from data.contacts import Contact, MergeSuggestion, MessengerHandle
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


def _login(client, user_id):
    with client.session_transaction() as s:
        s['user_id'] = user_id


@pytest.fixture
def setup_two_contacts_with_suggestion(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    c1 = Contact(user_id=u.id, display_name="Иван")
    c2 = Contact(user_id=u.id, display_name="Иванn")
    db.add_all([c1, c2])
    db.commit()
    h1 = MessengerHandle(contact_id=c1.id, user_id=u.id,
                         messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван")
    h2 = MessengerHandle(contact_id=c2.id, user_id=u.id,
                         messenger_name="Max", sender_raw="Иванn", sender_normalized="иванn")
    db.add_all([h1, h2])
    db.commit()
    sug = MergeSuggestion(user_id=u.id, source_handle_id=h2.id,
                          target_contact_id=c1.id, score=0.9, status="pending")
    db.add(sug)
    db.commit()
    out = (u.id, c1.id, c2.id, h1.id, h2.id, sug.id)
    db.close()
    return out


def test_manage_page_lists_handles_and_suggestions(client, setup_two_contacts_with_suggestion):
    user_id, *_ = setup_two_contacts_with_suggestion
    _login(client, user_id)
    response = client.get('/contacts/manage')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    assert "Иван" in body
    assert "Иванn" in body
    assert "Telegram" in body
    assert "Max" in body


def test_manage_requires_login(client):
    response = client.get('/contacts/manage')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
