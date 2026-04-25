import os

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


def test_download_page_is_public(client):
    r = client.get('/download')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert '/download/skillwood.apk' in body


def test_download_apk_returns_404_when_file_missing(client, tmp_path, monkeypatch):
    # Перенаправим dist в пустую temp-директорию.
    monkeypatch.chdir(tmp_path)
    r = client.get('/download/skillwood.apk')
    assert r.status_code == 404


def test_download_apk_returns_file_when_present(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "skillwood.apk").write_bytes(b"PK\x03\x04fakeapk")
    r = client.get('/download/skillwood.apk')
    assert r.status_code == 200
    assert r.data == b"PK\x03\x04fakeapk"
