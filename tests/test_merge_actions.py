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
def two_contacts(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    c1 = Contact(user_id=u.id, display_name="A")
    c2 = Contact(user_id=u.id, display_name="B")
    db.add_all([c1, c2])
    db.commit()
    h1 = MessengerHandle(contact_id=c1.id, user_id=u.id,
                         messenger_name="Telegram", sender_raw="A", sender_normalized="a")
    h2 = MessengerHandle(contact_id=c2.id, user_id=u.id,
                         messenger_name="Max", sender_raw="B", sender_normalized="b")
    db.add_all([h1, h2])
    db.commit()
    out = (u.id, c1.id, c2.id, h1.id, h2.id)
    db.close()
    return out


def test_rename_changes_display_name(client, two_contacts):
    user_id, c1_id, *_ = two_contacts
    _login(client, user_id)
    r = client.post(f'/contacts/{c1_id}/rename', data={"display_name": "NewName"})
    assert r.status_code in (200, 302)

    db = db_sessions.create_session()
    try:
        c = db.get(Contact, c1_id)
        assert c.display_name == "NewName"
    finally:
        db.close()


def test_rename_404_for_other_user(client, app, two_contacts):
    _, c1_id, *_ = two_contacts
    db = db_sessions.create_session()
    other = User(name="O", surname="U", sex="male", email="o@e.com", hashed_password="x")
    db.add(other)
    db.commit()
    other_id = other.id
    db.close()
    _login(client, other_id)
    r = client.post(f'/contacts/{c1_id}/rename', data={"display_name": "X"})
    assert r.status_code == 404


def test_merge_moves_handles_and_deletes_source(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, h2_id = two_contacts
    _login(client, user_id)
    r = client.post('/contacts/merge', data={"source_id": c1_id, "target_id": c2_id})
    assert r.status_code in (200, 302)

    db = db_sessions.create_session()
    try:
        assert db.query(Contact).filter(Contact.id == c1_id).first() is None
        assert db.query(Contact).filter(Contact.id == c2_id).first() is not None
        h1 = db.get(MessengerHandle, h1_id)
        assert h1.contact_id == c2_id
    finally:
        db.close()


def test_merge_400_when_same_source_target(client, two_contacts):
    user_id, c1_id, *_ = two_contacts
    _login(client, user_id)
    r = client.post('/contacts/merge', data={"source_id": c1_id, "target_id": c1_id})
    assert r.status_code == 400


def test_merge_404_across_users(client, app, two_contacts):
    user_id, c1_id, c2_id, *_ = two_contacts
    db = db_sessions.create_session()
    other = User(name="O", surname="U", sex="male", email="o@e.com", hashed_password="x")
    db.add(other)
    db.commit()
    other_c = Contact(user_id=other.id, display_name="X")
    db.add(other_c)
    db.commit()
    other_c_id = other_c.id
    db.close()

    _login(client, user_id)
    r = client.post('/contacts/merge', data={"source_id": c1_id, "target_id": other_c_id})
    assert r.status_code == 404


def test_merge_dismisses_dangling_suggestions(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, h2_id = two_contacts
    db = db_sessions.create_session()
    sug = MergeSuggestion(user_id=user_id, source_handle_id=h2_id,
                          target_contact_id=c1_id, score=0.9, status="pending")
    db.add(sug)
    db.commit()
    sug_id = sug.id
    db.close()

    _login(client, user_id)
    client.post('/contacts/merge', data={"source_id": c1_id, "target_id": c2_id})

    db = db_sessions.create_session()
    try:
        s = db.get(MergeSuggestion, sug_id)
        assert s.status == "dismissed"
    finally:
        db.close()


def test_handle_move_changes_contact(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, h2_id = two_contacts
    _login(client, user_id)
    r = client.post(f'/contacts/handles/{h1_id}/move', data={"target_contact_id": c2_id})
    assert r.status_code in (200, 302)

    db = db_sessions.create_session()
    try:
        h = db.get(MessengerHandle, h1_id)
        assert h.contact_id == c2_id
    finally:
        db.close()


def test_handle_move_deletes_emptied_source(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, _ = two_contacts
    _login(client, user_id)
    client.post(f'/contacts/handles/{h1_id}/move', data={"target_contact_id": c2_id})

    db = db_sessions.create_session()
    try:
        assert db.query(Contact).filter(Contact.id == c1_id).first() is None
    finally:
        db.close()


def test_handle_move_keeps_source_with_other_handles(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, _ = two_contacts
    db = db_sessions.create_session()
    extra = MessengerHandle(contact_id=c1_id, user_id=user_id,
                            messenger_name="Telegram", sender_raw="A2",
                            sender_normalized="a2")
    db.add(extra)
    db.commit()
    db.close()

    _login(client, user_id)
    client.post(f'/contacts/handles/{h1_id}/move', data={"target_contact_id": c2_id})

    db = db_sessions.create_session()
    try:
        assert db.query(Contact).filter(Contact.id == c1_id).first() is not None
    finally:
        db.close()


def test_handle_move_dismisses_dangling_suggestion(client, two_contacts):
    user_id, c1_id, c2_id, h1_id, h2_id = two_contacts
    db = db_sessions.create_session()
    sug = MergeSuggestion(user_id=user_id, source_handle_id=h2_id,
                          target_contact_id=c1_id, score=0.9, status="pending")
    db.add(sug)
    db.commit()
    sug_id = sug.id
    db.close()

    _login(client, user_id)
    client.post(f'/contacts/handles/{h1_id}/move', data={"target_contact_id": c2_id})

    db = db_sessions.create_session()
    try:
        s = db.get(MergeSuggestion, sug_id)
        assert s.status == "dismissed"
    finally:
        db.close()


def test_handle_move_noop_when_target_equals_current(client, two_contacts):
    user_id, c1_id, _, h1_id, _ = two_contacts
    _login(client, user_id)
    r = client.post(f'/contacts/handles/{h1_id}/move', data={"target_contact_id": c1_id})
    assert r.status_code in (200, 302)

    db = db_sessions.create_session()
    try:
        assert db.query(Contact).filter(Contact.id == c1_id).first() is not None
        h = db.get(MessengerHandle, h1_id)
        assert h.contact_id == c1_id
    finally:
        db.close()
