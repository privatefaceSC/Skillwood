import pytest
from sqlalchemy.exc import IntegrityError

from data.devices import Device
from data.users import User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_create_device(db_session):
    user = _make_user(db_session)
    d = Device(user_id=user.id, name="Xiaomi Pad",
               token_hash="a" * 64)
    db_session.add(d)
    db_session.commit()
    assert d.id is not None
    assert d.created_at is not None
    assert d.last_seen_ip is None
    assert d.last_seen_at is None


def test_device_token_hash_is_unique(db_session):
    user = _make_user(db_session)
    db_session.add(Device(user_id=user.id, name="A", token_hash="z" * 64))
    db_session.commit()
    db_session.add(Device(user_id=user.id, name="B", token_hash="z" * 64))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_device_belongs_to_user(db_session):
    user = _make_user(db_session)
    d = Device(user_id=user.id, name="Xiaomi Pad", token_hash="a" * 64)
    db_session.add(d)
    db_session.commit()
    assert d.user_id == user.id
