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
def setup_pending_suggestion(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    c1 = Contact(user_id=u.id, display_name="A")
    c2 = Contact(user_id=u.id, display_name="B")
    db.add_all([c1, c2])
    db.commit()
    h2 = MessengerHandle(contact_id=c2.id, user_id=u.id,
                         messenger_name="Max", sender_raw="B", sender_normalized="b")
    db.add(h2)
    db.commit()
    sug = MergeSuggestion(user_id=u.id, source_handle_id=h2.id,
                          target_contact_id=c1.id, score=0.9, status="pending")
    db.add(sug)
    db.commit()
    out = (u.id, c1.id, c2.id, h2.id, sug.id)
    db.close()
    return out


def test_dismiss_marks_status(client, setup_pending_suggestion):
    user_id, _, _, _, sug_id = setup_pending_suggestion
    _login(client, user_id)
    r = client.post(f'/contacts/suggestions/{sug_id}/dismiss')
    assert r.status_code in (200, 302)
    db = db_sessions.create_session()
    try:
        assert db.get(MergeSuggestion, sug_id).status == "dismissed"
    finally:
        db.close()


def test_accept_performs_merge(client, setup_pending_suggestion):
    user_id, c1_id, c2_id, h2_id, sug_id = setup_pending_suggestion
    _login(client, user_id)
    r = client.post(f'/contacts/suggestions/{sug_id}/accept')
    assert r.status_code in (200, 302)
    db = db_sessions.create_session()
    try:
        assert db.get(Contact, c2_id) is None
        assert db.get(Contact, c1_id) is not None
        h2 = db.get(MessengerHandle, h2_id)
        assert h2.contact_id == c1_id
        assert db.get(MergeSuggestion, sug_id).status == "accepted"
    finally:
        db.close()


def test_dismiss_404_for_other_user(client, app, setup_pending_suggestion):
    _, _, _, _, sug_id = setup_pending_suggestion
    db = db_sessions.create_session()
    other = User(name="O", surname="U", sex="male", email="o@e.com", hashed_password="x")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()
    _login(client, other_id)
    r = client.post(f'/contacts/suggestions/{sug_id}/dismiss')
    assert r.status_code == 404
