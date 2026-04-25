def test_create_app_returns_flask_app():
    from main import create_app
    app = create_app(":memory:")
    assert app is not None
    assert app.config['SECRET_KEY']


def test_create_app_root_renders_main_menu_template():
    from main import create_app
    app = create_app(":memory:")
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'<!DOCTYPE html>' in response.data
    assert response.content_length > 0
