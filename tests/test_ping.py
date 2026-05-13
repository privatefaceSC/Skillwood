import pytest

from data import db_sessions


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


def test_api_ping_is_public_and_returns_ok(client):
    response = client.get('/api/ping')
    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'service': 'skillwood'}
