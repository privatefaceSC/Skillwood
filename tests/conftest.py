import pytest

from data import db_sessions


@pytest.fixture
def db_session():
    """Per-test in-memory SQLite session."""
    db_sessions._reset_for_tests()
    db_sessions.global_init(":memory:")
    session = db_sessions.create_session()
    yield session
    session.close()
    db_sessions._reset_for_tests()
