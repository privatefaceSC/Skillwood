# Android-клиент Skillwood — план имплементации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собственное Android-приложение, которое слушает уведомления планшета и шлёт их в Skillwood-сервер с device-token аутентификацией; раздача APK через сам сервер по `/download`.

**Architecture:** Серверная часть — модель `Device` с sha256-хешем токена, новые маршруты `/api/connect`, `/api/me`, `/download`, обновлённый `POST /add` с Bearer-аутентификацией. Клиент — Kotlin + classic Views, NotificationListenerService + ForegroundService + локальная очередь, OkHttp для HTTP, Robolectric для JVM-тестов.

**Tech Stack:** Python 3.13, Flask 3.1, SQLAlchemy 2.0, pytest (сервер). Kotlin 2.0, AndroidX, OkHttp 4.12, kotlinx-coroutines, WorkManager 2.9, Robolectric 4.13, JUnit 4 (Android).

**Reference:** [docs/superpowers/specs/2026-04-25-android-client-design.md](../specs/2026-04-25-android-client-design.md)

> **Замечание про коммиты:** в этом проекте все `git commit` делает пользователь вручную. Финальный шаг каждой задачи — «прогнать тесты». Когда тесты зелёные — пользователь сам решает, когда сделать коммит. Шагов с `git commit` в плане нет.

---

## Фаза 1 — Серверная часть

### Task 1: Модель `Device`

**Files:**
- Create: `data/devices.py`
- Modify: `data/__all_models.py`
- Create: `tests/test_devices_model.py`

- [ ] **Step 1: Падающий тест на модель**

`tests/test_devices_model.py`:

```python
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
```

- [ ] **Step 2: Запустить — должно падать**

```bash
.venv/Scripts/pytest tests/test_devices_model.py -v
```

Ожидается: `ImportError: cannot import name 'Device' from 'data.devices'`.

- [ ] **Step 3: Создать `data/devices.py`**

```python
import datetime

import sqlalchemy

from .db_sessions import SqlAlchemyBase


class Device(SqlAlchemyBase):
    __tablename__ = 'devices'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer,
                                sqlalchemy.ForeignKey("users.id"), nullable=False)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    token_hash = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True, index=True)
    last_seen_ip = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    last_seen_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime,
                                   default=datetime.datetime.now, nullable=False)
```

- [ ] **Step 4: Зарегистрировать в `data/__all_models.py`**

Заменить содержимое:

```python
from . import users
from . import contacts
from . import devices
```

- [ ] **Step 5: Запустить — должно проходить**

```bash
.venv/Scripts/pytest tests/test_devices_model.py -v
```

Ожидается: `3 passed`.

- [ ] **Step 6: Полный прогон тестов проекта**

```bash
.venv/Scripts/pytest
```

Все тесты должны проходить (60+ существующих + 3 новых).

---

### Task 2: Хелперы `generate_token` и `hash_token`

**Files:**
- Modify: `data/devices.py`
- Create: `tests/test_devices_token.py`

- [ ] **Step 1: Падающий тест**

`tests/test_devices_token.py`:

```python
from data.devices import generate_token, hash_token


def test_generate_token_returns_long_url_safe_string():
    t = generate_token()
    assert isinstance(t, str)
    # secrets.token_urlsafe(32) → 43 символа base64-url
    assert len(t) >= 40
    # Только URL-safe символы
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert all(c in allowed for c in t)


def test_generate_token_is_random():
    a = generate_token()
    b = generate_token()
    assert a != b


def test_hash_token_is_sha256_hex():
    h = hash_token("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_token_is_deterministic():
    assert hash_token("hello") == hash_token("hello")


def test_hash_token_differs_for_different_input():
    assert hash_token("a") != hash_token("b")
```

- [ ] **Step 2: Запустить — должно падать**

```bash
.venv/Scripts/pytest tests/test_devices_token.py -v
```

Ожидается: `ImportError`.

- [ ] **Step 3: Дописать в `data/devices.py`**

В конец файла добавить:

```python
import hashlib
import secrets


def generate_token() -> str:
    """Возвращает случайный URL-safe токен ~43 символа."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """SHA-256 hex-digest от токена. Используется для хранения в БД."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Прогон тестов**

```bash
.venv/Scripts/pytest tests/test_devices_token.py -v
```

Ожидается: `5 passed`.

---

### Task 3: `POST /api/connect`

**Files:**
- Modify: `main.py`
- Create: `tests/test_api_connect.py`

- [ ] **Step 1: Падающий тест**

`tests/test_api_connect.py`:

```python
import pytest

from data import db_sessions
from data.devices import Device, hash_token
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


@pytest.fixture
def user_with_code(app):
    db = db_sessions.create_session()
    u = User(name="Test", surname="User", sex="male",
             email="t@e.com", hashed_password="x", connect_code="12345678")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_api_connect_creates_device(client, user_with_code):
    r = client.post('/api/connect', json={
        "code": "12345678", "device_name": "Xiaomi Pad",
    })
    assert r.status_code == 200
    data = r.get_json()
    assert "token" in data
    assert len(data["token"]) >= 40
    assert data["user"]["name"] == "Test"
    assert data["device"]["name"] == "Xiaomi Pad"

    db = db_sessions.create_session()
    try:
        devices = db.query(Device).all()
        assert len(devices) == 1
        assert devices[0].user_id == user_with_code
        assert devices[0].name == "Xiaomi Pad"
        assert devices[0].token_hash == hash_token(data["token"])
    finally:
        db.close()


def test_api_connect_rejects_unknown_code(client):
    r = client.post('/api/connect', json={"code": "99999999", "device_name": "X"})
    assert r.status_code == 404


def test_api_connect_rejects_empty_code(client):
    r = client.post('/api/connect', json={"code": "", "device_name": "X"})
    assert r.status_code == 400


def test_api_connect_rejects_empty_device_name(client, user_with_code):
    r = client.post('/api/connect', json={"code": "12345678", "device_name": ""})
    assert r.status_code == 400


def test_api_connect_creates_distinct_tokens_for_two_devices(client, user_with_code):
    r1 = client.post('/api/connect', json={"code": "12345678", "device_name": "A"})
    r2 = client.post('/api/connect', json={"code": "12345678", "device_name": "B"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["token"] != r2.get_json()["token"]
```

- [ ] **Step 2: Запустить — падает**

```bash
.venv/Scripts/pytest tests/test_api_connect.py -v
```

Ожидается: 5 fail (маршрута нет).

- [ ] **Step 3: Реализовать маршрут в `main.py`**

В `register_routes(app)` после существующего `/api/ping` добавить:

```python
    @app.route('/api/connect', methods=['POST'])
    def api_connect():
        from data.devices import Device, generate_token, hash_token

        body = request.get_json(silent=True) or {}
        code = (body.get('code') or '').strip()
        device_name = (body.get('device_name') or '').strip()
        if not code or not device_name:
            return jsonify({'error': 'code and device_name required'}), 400

        db = get_db()
        user = db.query(User).filter(User.connect_code == code).first()
        if not user:
            return jsonify({'error': 'unknown code'}), 404

        token = generate_token()
        device = Device(user_id=user.id, name=device_name,
                        token_hash=hash_token(token))
        db.add(device)
        db.commit()
        return jsonify({
            'token': token,
            'user': {'id': user.id, 'name': user.name},
            'device': {'id': device.id, 'name': device.name},
        })
```

- [ ] **Step 4: Прогон**

```bash
.venv/Scripts/pytest tests/test_api_connect.py -v
```

Ожидается: `5 passed`.

---

### Task 4: `GET /api/me` + `POST /add` с Bearer-токеном

**Files:**
- Modify: `main.py`
- Create: `tests/test_api_me.py`
- Create: `tests/test_add_bearer.py`

- [ ] **Step 1: Падающие тесты `/api/me`**

`tests/test_api_me.py`:

```python
import pytest

from data import db_sessions
from data.devices import Device, hash_token
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


@pytest.fixture
def user_and_token(app):
    db = db_sessions.create_session()
    u = User(name="Test", surname="U", sex="male",
             email="t@e.com", hashed_password="x")
    db.add(u)
    db.commit()
    raw_token = "test-token-1234567890abcdef"
    d = Device(user_id=u.id, name="Pad", token_hash=hash_token(raw_token))
    db.add(d)
    db.commit()
    out = (u.id, raw_token)
    db.close()
    return out


def test_me_returns_user_info_with_valid_token(client, user_and_token):
    _, token = user_and_token
    r = client.get('/api/me', headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["user"]["name"] == "Test"
    assert data["device"]["name"] == "Pad"


def test_me_returns_401_without_header(client):
    r = client.get('/api/me')
    assert r.status_code == 401


def test_me_returns_401_with_invalid_token(client, user_and_token):
    r = client.get('/api/me', headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 401


def test_me_returns_401_with_malformed_header(client, user_and_token):
    _, token = user_and_token
    r = client.get('/api/me', headers={"Authorization": token})  # без Bearer
    assert r.status_code == 401
```

- [ ] **Step 2: Падающие тесты `/add` с Bearer**

`tests/test_add_bearer.py`:

```python
from datetime import datetime

import pytest

from data import db_sessions
from data.contacts import Contact, MessengerHandle
from data.devices import Device, hash_token
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
def user_and_device(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x")
    db.add(u)
    db.commit()
    raw_token = "raw-token-xyz"
    d = Device(user_id=u.id, name="Pad", token_hash=hash_token(raw_token))
    db.add(d)
    db.commit()
    out = (u.id, d.id, raw_token)
    db.close()
    return out


def test_add_with_bearer_records_message(client, user_and_device):
    _, _, token = user_and_device
    r = client.post('/add',
                    headers={"Authorization": f"Bearer {token}"},
                    data={"sender": "Иван", "text": "привет",
                          "messenger_name": "Telegram"})
    assert r.status_code == 200
    db = db_sessions.create_session()
    try:
        msgs = db.query(Messages).all()
        assert len(msgs) == 1
        assert msgs[0].text == "привет"
        assert msgs[0].handle_id is not None
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
    finally:
        db.close()


def test_add_with_invalid_bearer_returns_401(client):
    r = client.post('/add',
                    headers={"Authorization": "Bearer not-a-real-token"},
                    data={"sender": "X", "text": "Y", "messenger_name": "Z"})
    assert r.status_code == 401


def test_add_without_bearer_falls_back_to_ip(client, app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="b@e.com",
             hashed_password="x", tablet_ip="127.0.0.1")
    db.add(u)
    db.commit()
    db.close()
    r = client.post('/add', data={"sender": "X", "text": "Y", "messenger_name": "Z"})
    assert r.status_code == 200
    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 1
    finally:
        db.close()


def test_add_with_bearer_updates_device_last_seen(client, user_and_device):
    _, device_id, token = user_and_device
    client.post('/add',
                headers={"Authorization": f"Bearer {token}"},
                data={"sender": "Иван", "text": "привет",
                      "messenger_name": "Telegram"})
    db = db_sessions.create_session()
    try:
        d = db.get(Device, device_id)
        assert d.last_seen_ip is not None
        assert d.last_seen_at is not None
    finally:
        db.close()
```

- [ ] **Step 3: Прогон — падает**

```bash
.venv/Scripts/pytest tests/test_api_me.py tests/test_add_bearer.py -v
```

Ожидается: 4 + 4 = 8 fail.

- [ ] **Step 4: Реализовать `/api/me` и обновить `/add` в `main.py`**

В `register_routes(app)` после `/api/connect` добавить хелпер и `/api/me`:

```python
    def _device_from_bearer(db):
        """Достаёт Device по Authorization: Bearer ... или возвращает None."""
        from data.devices import Device, hash_token
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return None
        token = auth[len('Bearer '):].strip()
        if not token:
            return None
        return db.query(Device).filter(Device.token_hash == hash_token(token)).first()

    @app.route('/api/me', methods=['GET'])
    def api_me():
        db = get_db()
        device = _device_from_bearer(db)
        if device is None:
            return jsonify({'error': 'unauthorized'}), 401
        user = db.query(User).filter(User.id == device.user_id).first()
        return jsonify({
            'user': {'id': user.id, 'name': user.name},
            'device': {'id': device.id, 'name': device.name},
        })
```

Затем заменить функцию `add_message` на двухрежимный вариант:

```python
    @app.route('/add', methods=['POST'])
    def add_message():
        from data.contacts import record_message

        sender = request.form.get('sender')
        text_value = request.form.get('text')
        messenger_name = request.form.get('messenger_name')

        if not sender or not text_value or not messenger_name:
            return 'Bad Request', 400

        db = get_db()
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            device = _device_from_bearer(db)
            if device is None:
                return 'Unauthorized', 401
            device.last_seen_ip = request.remote_addr
            device.last_seen_at = datetime.now()
            user_id = device.user_id
            db.commit()
        else:
            tablet_ip = request.remote_addr
            user = db.query(User).filter(User.tablet_ip == tablet_ip).first()
            if not user:
                print(f"Неизвестное устройство с IP: {tablet_ip}")
                return 'OK', 200
            user_id = user.id

        record_message(db, user_id, messenger_name, sender, text_value)
        return 'OK', 200
```

ВАЖНО: `_device_from_bearer` должна быть определена ДО `api_me` и `add_message`.

- [ ] **Step 5: Прогон новых тестов**

```bash
.venv/Scripts/pytest tests/test_api_me.py tests/test_add_bearer.py -v
```

Ожидается: `8 passed`.

- [ ] **Step 6: Полный прогон**

```bash
.venv/Scripts/pytest
```

Все существующие + новые должны проходить.

---

### Task 5: Страница `/download` и раздача APK

**Files:**
- Modify: `main.py`
- Create: `templates/download.html`
- Create: `tests/test_download.py`

- [ ] **Step 1: Падающие тесты**

`tests/test_download.py`:

```python
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
```

- [ ] **Step 2: Запустить — падает**

```bash
.venv/Scripts/pytest tests/test_download.py -v
```

Ожидается: 3 fail (маршрутов нет).

- [ ] **Step 3: Создать `templates/download.html`**

```html
{% extends 'base.html' %}

{% block title %}Скачать клиент Skillwood{% endblock %}

{% block body %}
<div class="container" style="max-width: 720px;">
    <div class="card shadow-sm border-0 mb-3">
        <div class="card-body">
            <h2 class="mb-3">Клиент Skillwood для Android</h2>
            <p class="text-muted">
                Маленькое приложение, которое слушает уведомления вашего планшета и
                пересылает их на сайт Skillwood. Один установочный файл, никаких
                настроек триггеров и фильтров.
            </p>
            <div class="d-grid mb-3">
                <a href="/download/skillwood.apk" class="btn btn-primary btn-lg">
                    Скачать APK
                </a>
            </div>
        </div>
    </div>

    <div class="card shadow-sm border-0">
        <div class="card-body">
            <h5>Как установить</h5>
            <ol>
                <li>Откройте эту страницу с планшета (или скопируйте APK на него).</li>
                <li>Нажмите «Скачать APK» и подтвердите загрузку.</li>
                <li>Откройте скачанный файл — Android спросит разрешение
                    «Установка из неизвестных источников». Дайте разрешение.</li>
                <li>Запустите Skillwood-клиент. Введите адрес сервера, ваш код
                    подключения (8 цифр с сайта) и имя устройства.</li>
                <li>Согласитесь на запрос «Доступ к уведомлениям».</li>
                <li>Готово — на главной странице сайта появятся ваши контакты.</li>
            </ol>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Реализовать маршруты в `main.py`**

В `register_routes(app)` после `/api/me` добавить:

```python
    @app.route('/download')
    def download_index():
        return render_template('download.html')

    @app.route('/download/skillwood.apk')
    def download_apk():
        import os
        from flask import send_from_directory, abort
        path = os.path.join(os.getcwd(), 'dist', 'skillwood.apk')
        if not os.path.exists(path):
            abort(404)
        return send_from_directory(
            os.path.join(os.getcwd(), 'dist'),
            'skillwood.apk',
            as_attachment=True,
            mimetype='application/vnd.android.package-archive',
        )
```

- [ ] **Step 5: Прогон**

```bash
.venv/Scripts/pytest tests/test_download.py -v
```

Ожидается: `3 passed`.

---

### Task 6: Кнопки «Скачать клиент» в `/home` и `/code`

**Files:**
- Modify: `templates/index.html`
- Modify: `templates/code.html`
- Create: `tests/test_download_links.py`

- [ ] **Step 1: Падающий тест**

`tests/test_download_links.py`:

```python
import pytest

from data import db_sessions
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


def _make_user(app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="t@e.com",
             hashed_password="x", connect_code="12345678", tablet_ip=None)
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_home_has_download_link(client, app):
    uid = _make_user(app)
    with client.session_transaction() as s:
        s['user_id'] = uid
    r = client.get('/home')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert '/download' in body


def test_code_has_download_link(client, app):
    uid = _make_user(app)
    with client.session_transaction() as s:
        s['user_id'] = uid
    r = client.get('/code')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert '/download' in body
```

- [ ] **Step 2: Падает**

```bash
.venv/Scripts/pytest tests/test_download_links.py -v
```

Ожидается: 2 fail.

- [ ] **Step 3: Добавить ссылку в `templates/index.html`**

После блока с тремя карточками-сводками (`<div class="row g-3">...</div>`) добавить:

```html
    <div class="card shadow-sm border-0 mt-3">
        <div class="card-body d-flex justify-content-between align-items-center">
            <div>
                <strong>Клиент для Android</strong>
                <div class="text-muted small">Сами уведомления — без MacroDroid.</div>
            </div>
            <a href="/download" class="btn btn-outline-primary">Скачать</a>
        </div>
    </div>
```

- [ ] **Step 4: Добавить ссылку в `templates/code.html`**

После `<hr class="my-4">` добавить:

```html
<p class="mt-4">
    Хотите быстрее? Поставьте <a href="/download">Skillwood-клиент для Android</a>
    и введите этот код в приложении.
</p>
```

- [ ] **Step 5: Прогон**

```bash
.venv/Scripts/pytest tests/test_download_links.py -v
```

Ожидается: `2 passed`.

- [ ] **Step 6: Полный прогон**

```bash
.venv/Scripts/pytest
```

Все тесты зелёные (60+ существующих + ~20 новых).

---

## Фаза 2 — Каркас Android-проекта

### Task 7: Gradle-каркас

> **Подготовка перед задачей:** установить Android Studio (бесплатно от Google, ~5 GB). При установке выбрать «Standard» — он сам поставит JDK 17, Android SDK и Build Tools. Если уже стоит — пропустить.

**Files:**
- Create: `android/.gitignore`
- Create: `android/settings.gradle.kts`
- Create: `android/build.gradle.kts`
- Create: `android/gradle.properties`
- Create: `android/gradle/wrapper/gradle-wrapper.properties`
- Create: `android/app/build.gradle.kts`
- Create: `android/app/proguard-rules.pro`
- Create: `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/main/res/values/strings.xml`
- Create: `android/app/src/main/res/values/themes.xml`
- Create: `android/app/src/main/res/values/colors.xml`
- Create: `android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
- Create: `android/app/src/main/res/drawable/ic_launcher_background.xml`
- Create: `android/app/src/main/res/drawable/ic_launcher_foreground.xml`
- Modify: корневой `.gitignore`

- [ ] **Step 1: `android/.gitignore`**

```
.gradle/
build/
.idea/
local.properties
*.iml
captures/
.cxx/
```

- [ ] **Step 2: `android/settings.gradle.kts`**

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Skillwood"
include(":app")
```

- [ ] **Step 3: `android/build.gradle.kts`**

```kotlin
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
}
```

- [ ] **Step 4: `android/gradle.properties`**

```properties
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=true
kotlin.code.style=official
android.nonTransitiveRClass=true
```

- [ ] **Step 5: `android/gradle/wrapper/gradle-wrapper.properties`**

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.9-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

- [ ] **Step 6: `android/app/build.gradle.kts`**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.skillwood.client"
    compileSdk = 34

    defaultConfig {
        applicationId = "io.skillwood.client"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"),
                          "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("androidx.test.ext:junit:1.2.1")
}
```

- [ ] **Step 7: `android/app/proguard-rules.pro`**

```
# Skillwood — пока не используем R8, но файл должен существовать.
```

- [ ] **Step 8: `android/app/src/main/AndroidManifest.xml`** (минимальный)

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"/>
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED"/>

    <application
        android:label="@string/app_name"
        android:icon="@mipmap/ic_launcher"
        android:theme="@style/Theme.Skillwood"
        android:allowBackup="true"
        android:usesCleartextTraffic="true">
        <!-- Заглушка — настоящие activity/services будут добавлены в следующих задачах. -->
    </application>
</manifest>
```

ВАЖНО: `usesCleartextTraffic="true"` — чтобы клиент мог ходить на `http://` (а не только `https://`). Учебный сервер без TLS.

- [ ] **Step 9: `android/app/src/main/res/values/strings.xml`**

```xml
<resources>
    <string name="app_name">Skillwood</string>
</resources>
```

- [ ] **Step 10: `android/app/src/main/res/values/themes.xml`**

```xml
<resources>
    <style name="Theme.Skillwood" parent="Theme.MaterialComponents.DayNight.NoActionBar">
        <item name="colorPrimary">@color/skillwood_primary</item>
        <item name="colorOnPrimary">#FFFFFF</item>
        <item name="android:statusBarColor">@color/skillwood_primary</item>
    </style>
</resources>
```

- [ ] **Step 11: `android/app/src/main/res/values/colors.xml`**

```xml
<resources>
    <color name="skillwood_primary">#3B82F6</color>
    <color name="skillwood_success">#10B981</color>
    <color name="skillwood_danger">#EF4444</color>
    <color name="skillwood_neutral">#6B7280</color>
</resources>
```

- [ ] **Step 12: Адаптивная иконка** — три файла:

`android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
```

`android/app/src/main/res/drawable/ic_launcher_background.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android"
       android:shape="rectangle">
    <solid android:color="#3B82F6"/>
</shape>
```

`android/app/src/main/res/drawable/ic_launcher_foreground.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
        android:width="108dp" android:height="108dp"
        android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#FFFFFF"
          android:pathData="M54,30 L72,54 L54,78 L36,54 Z"/>
</vector>
```

- [ ] **Step 13: Дополнить корневой `.gitignore`**

В корневой `.gitignore` (или `.git/info/exclude`) добавить:

```
android/.gradle/
android/build/
android/app/build/
android/.idea/
android/local.properties
android/*.iml
dist/
```

- [ ] **Step 14: Открыть проект в Android Studio**

Инструкция инженеру:
1. Открой Android Studio → File → Open → выбери папку `android/`.
2. Studio предложит загрузить Gradle Wrapper, JDK 17 и Android SDK 34. Соглашайся.
3. После «Gradle Sync» — в нижней панели должно быть «BUILD SUCCESSFUL».
4. Если синхронизация прошла — каркас рабочий.

- [ ] **Step 15: Проверить сборку из командной строки**

После того как Android Studio при первом открытии создаст `gradlew`/`gradlew.bat`/`gradle/wrapper/gradle-wrapper.jar`, прогнать:

```bash
cd android
./gradlew tasks --no-daemon
```

Ожидается: список задач без ошибок (Build Setup tasks, Help tasks).

---

### Task 8: Application-класс и навигационные строки

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/SkillwoodApp.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`
- Modify: `android/app/src/main/res/values/strings.xml`

- [ ] **Step 1: Создать `SkillwoodApp.kt`**

`android/app/src/main/java/io/skillwood/client/SkillwoodApp.kt`:

```kotlin
package io.skillwood.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class SkillwoodApp : Application() {
    override fun onCreate() {
        super.onCreate()
        ensureNotificationChannel()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(
            CHANNEL_FOREGROUND,
            getString(R.string.channel_foreground),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.channel_foreground_desc)
            setShowBadge(false)
        }
        nm.createNotificationChannel(ch)
    }

    companion object {
        const val CHANNEL_FOREGROUND = "skillwood_foreground"
    }
}
```

- [ ] **Step 2: Зарегистрировать Application в AndroidManifest**

В `<application>` добавить атрибут `android:name=".SkillwoodApp"`:

```xml
<application
    android:name=".SkillwoodApp"
    android:label="@string/app_name"
    android:icon="@mipmap/ic_launcher"
    android:theme="@style/Theme.Skillwood"
    android:allowBackup="true"
    android:usesCleartextTraffic="true">
```

- [ ] **Step 3: Дополнить строки в `strings.xml`**

Заменить содержимое `android/app/src/main/res/values/strings.xml`:

```xml
<resources>
    <string name="app_name">Skillwood</string>

    <!-- Уведомление foreground-сервиса -->
    <string name="channel_foreground">Skillwood работает</string>
    <string name="channel_foreground_desc">Постоянное уведомление, чтобы Android не выгружал слушатель в фоне.</string>
    <string name="foreground_title">Skillwood работает</string>
    <string name="foreground_text">Слушаем уведомления и пересылаем на сервер.</string>

    <!-- Главный экран — состояния -->
    <string name="state_setup_title">Подключите устройство</string>
    <string name="state_setup_desc">Откройте Skillwood в браузере, зарегистрируйтесь и введите данные ниже.</string>
    <string name="hint_server_url">Адрес сервера (например, http://192.168.1.3:5000)</string>
    <string name="hint_connect_code">Код подключения (8 цифр)</string>
    <string name="hint_device_name">Имя устройства</string>
    <string name="action_connect">Подключить</string>

    <string name="state_no_access_title">Нет доступа к уведомлениям</string>
    <string name="state_no_access_desc">Чтобы Skillwood мог пересылать уведомления, дайте ему доступ в системных настройках.</string>
    <string name="action_grant_access">Дать доступ</string>

    <string name="state_active_title">Skillwood активен</string>
    <string name="state_active_account">Аккаунт: %1$s</string>
    <string name="stat_sent">Отправлено: %1$d</string>
    <string name="stat_last_sent">Последнее: %1$s</string>
    <string name="stat_errors">Ошибок подряд: %1$d</string>
    <string name="stat_queue">В очереди: %1$d</string>
    <string name="action_test">Отправить тест</string>
    <string name="action_disconnect">Отключить устройство</string>

    <!-- Сообщения об ошибках -->
    <string name="error_network">Нет связи с сервером.</string>
    <string name="error_unknown_code">Сервер не знает такого кода.</string>
    <string name="error_unauthorized">Сервер отклонил токен.</string>
    <string name="error_server">Сервер ответил ошибкой.</string>
    <string name="error_unknown">Неизвестная ошибка.</string>

    <!-- Тестовое сообщение -->
    <string name="test_sender">Тест</string>
    <string name="test_text">Привет от Skillwood-клиента</string>
    <string name="test_messenger">Skillwood Test</string>
</resources>
```

- [ ] **Step 4: Пересинхронизировать Gradle**

В Android Studio: File → Sync Project with Gradle Files. Должно собраться без ошибок.

```bash
cd android
./gradlew compileDebugKotlin --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`.

---

## Фаза 3 — Бизнес-логика клиента (TDD)

### Task 9: `SettingsRepository`

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/SettingsRepository.kt`
- Create: `android/app/src/test/java/io/skillwood/client/SettingsRepositoryTest.kt`

- [ ] **Step 1: Падающий тест**

`android/app/src/test/java/io/skillwood/client/SettingsRepositoryTest.kt`:

```kotlin
package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class SettingsRepositoryTest {

    private lateinit var repo: SettingsRepository

    @Before
    fun setUp() {
        repo = SettingsRepository(ApplicationProvider.getApplicationContext())
        repo.clear()
    }

    @Test
    fun freshly_initialized_is_not_configured() {
        assertFalse(repo.isConfigured())
        assertNull(repo.deviceToken)
        assertNull(repo.serverUrl)
    }

    @Test
    fun stores_and_returns_credentials() {
        repo.serverUrl = "http://192.168.1.3:5000"
        repo.deviceToken = "tkn-xyz"
        repo.userName = "Defi"
        repo.deviceName = "Pad"
        assertTrue(repo.isConfigured())
        assertEquals("http://192.168.1.3:5000", repo.serverUrl)
        assertEquals("tkn-xyz", repo.deviceToken)
        assertEquals("Defi", repo.userName)
        assertEquals("Pad", repo.deviceName)
    }

    @Test
    fun record_success_increments_counter_and_resets_errors() {
        repo.recordError()
        repo.recordError()
        assertEquals(2, repo.errorsStreak)
        repo.recordSuccess()
        assertEquals(1, repo.sent)
        assertEquals(0, repo.errorsStreak)
    }

    @Test
    fun record_error_increments_errors_streak() {
        repo.recordError()
        repo.recordError()
        repo.recordError()
        assertEquals(3, repo.errorsStreak)
    }

    @Test
    fun clear_removes_token_and_resets_stats() {
        repo.deviceToken = "x"
        repo.recordSuccess()
        repo.recordError()
        repo.clear()
        assertNull(repo.deviceToken)
        assertEquals(0, repo.sent)
        assertEquals(0, repo.errorsStreak)
    }
}
```

- [ ] **Step 2: Реализовать `SettingsRepository`**

`android/app/src/main/java/io/skillwood/client/SettingsRepository.kt`:

```kotlin
package io.skillwood.client

import android.content.Context
import android.content.SharedPreferences

class SettingsRepository(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var serverUrl: String?
        get() = prefs.getString(KEY_URL, null)
        set(value) { prefs.edit().putString(KEY_URL, value).apply() }

    var deviceToken: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) { prefs.edit().putString(KEY_TOKEN, value).apply() }

    var userName: String?
        get() = prefs.getString(KEY_USER_NAME, null)
        set(value) { prefs.edit().putString(KEY_USER_NAME, value).apply() }

    var deviceName: String?
        get() = prefs.getString(KEY_DEVICE_NAME, null)
        set(value) { prefs.edit().putString(KEY_DEVICE_NAME, value).apply() }

    val sent: Long
        get() = prefs.getLong(KEY_SENT, 0)

    val errorsStreak: Int
        get() = prefs.getInt(KEY_ERRORS, 0)

    val lastSentAt: Long
        get() = prefs.getLong(KEY_LAST_SENT, 0)

    fun isConfigured(): Boolean = !deviceToken.isNullOrBlank()

    fun recordSuccess() {
        prefs.edit()
            .putLong(KEY_SENT, sent + 1)
            .putLong(KEY_LAST_SENT, System.currentTimeMillis())
            .putInt(KEY_ERRORS, 0)
            .apply()
    }

    fun recordError() {
        prefs.edit().putInt(KEY_ERRORS, errorsStreak + 1).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val PREFS = "skillwood"
        private const val KEY_URL = "server_url"
        private const val KEY_TOKEN = "device_token"
        private const val KEY_USER_NAME = "user_name"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_SENT = "stats_sent"
        private const val KEY_LAST_SENT = "stats_last_sent_at"
        private const val KEY_ERRORS = "stats_errors_streak"
    }
}
```

- [ ] **Step 3: Прогон тестов**

```bash
cd android
./gradlew :app:testDebugUnitTest --tests io.skillwood.client.SettingsRepositoryTest --no-daemon
```

Ожидается: `5 passed`. Первый запуск Robolectric долгий (скачивает Android-резолвер, ~2-3 минуты), последующие быстрые.

---

### Task 10: `Result` и `ApiClient`

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/Result.kt`
- Create: `android/app/src/main/java/io/skillwood/client/ApiClient.kt`
- Create: `android/app/src/test/java/io/skillwood/client/ApiClientTest.kt`

- [ ] **Step 1: Падающие тесты**

`android/app/src/test/java/io/skillwood/client/ApiClientTest.kt`:

```kotlin
package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ApiClientTest {

    private lateinit var server: MockWebServer
    private lateinit var settings: SettingsRepository
    private lateinit var client: ApiClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        settings = SettingsRepository(ApplicationProvider.getApplicationContext())
        settings.clear()
        settings.serverUrl = server.url("/").toString().trimEnd('/')
        client = ApiClient(settings)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun ping_success() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok": true}"""))
        val r = client.ping(settings.serverUrl!!)
        assertTrue(r is Result.Success)
    }

    @Test
    fun connect_success_returns_token() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"token":"abc","user":{"id":1,"name":"Defi"},"device":{"id":1,"name":"Pad"}}"""
        ))
        val r = client.connect(settings.serverUrl!!, "12345678", "Pad")
        assertTrue(r is Result.Success)
        val data = (r as Result.Success).value
        assertEquals("abc", data.token)
        assertEquals("Defi", data.userName)
    }

    @Test
    fun connect_unknown_code_returns_not_found() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":"unknown code"}"""))
        val r = client.connect(settings.serverUrl!!, "00000000", "Pad")
        assertTrue(r is Result.Error)
        assertEquals(Result.ErrorKind.NotFound, (r as Result.Error).kind)
    }

    @Test
    fun send_notification_with_token_sends_bearer_header() = runBlocking {
        settings.deviceToken = "MY-TOKEN"
        server.enqueue(MockResponse().setResponseCode(200).setBody("OK"))
        val r = client.sendNotification("Иван", "привет", "Telegram")
        assertTrue(r is Result.Success)
        val req = server.takeRequest()
        assertEquals("Bearer MY-TOKEN", req.getHeader("Authorization"))
        val body = req.body.readUtf8()
        assertTrue(body.contains("sender="))
        assertTrue(body.contains("messenger_name=Telegram"))
    }

    @Test
    fun send_notification_unauthorized_returns_unauthorized() = runBlocking {
        settings.deviceToken = "BAD"
        server.enqueue(MockResponse().setResponseCode(401))
        val r = client.sendNotification("a", "b", "c")
        assertTrue(r is Result.Error)
        assertEquals(Result.ErrorKind.Unauthorized, (r as Result.Error).kind)
    }
}
```

- [ ] **Step 2: Реализовать `Result`**

`android/app/src/main/java/io/skillwood/client/Result.kt`:

```kotlin
package io.skillwood.client

sealed class Result<out T> {
    data class Success<T>(val value: T) : Result<T>()
    data class Error(val message: String, val kind: ErrorKind) : Result<Nothing>()

    enum class ErrorKind { Network, Unauthorized, NotFound, BadRequest, Server, Unknown }
}
```

- [ ] **Step 3: Реализовать `ApiClient`**

`android/app/src/main/java/io/skillwood/client/ApiClient.kt`:

```kotlin
package io.skillwood.client

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

data class ConnectResponse(
    val token: String,
    val userName: String,
    val deviceId: Long,
    val deviceName: String,
)

data class MeResponse(val userName: String, val deviceName: String)

class ApiClient(private val settings: SettingsRepository) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .build()

    suspend fun ping(serverUrl: String): Result<Unit> = withContext(Dispatchers.IO) {
        execute(Request.Builder().url("$serverUrl/api/ping").get().build()) { _ ->
            Result.Success(Unit)
        }
    }

    suspend fun connect(serverUrl: String, code: String, deviceName: String): Result<ConnectResponse> =
        withContext(Dispatchers.IO) {
            val body = JSONObject(mapOf("code" to code, "device_name" to deviceName))
                .toString()
                .toRequestBody("application/json".toMediaType())
            execute(
                Request.Builder().url("$serverUrl/api/connect").post(body).build()
            ) { responseBody ->
                val json = JSONObject(responseBody)
                Result.Success(
                    ConnectResponse(
                        token = json.getString("token"),
                        userName = json.getJSONObject("user").getString("name"),
                        deviceId = json.getJSONObject("device").getLong("id"),
                        deviceName = json.getJSONObject("device").getString("name"),
                    )
                )
            }
        }

    suspend fun me(): Result<MeResponse> = withContext(Dispatchers.IO) {
        val url = settings.serverUrl ?: return@withContext err(Result.ErrorKind.Unknown, "no url")
        val token = settings.deviceToken ?: return@withContext err(Result.ErrorKind.Unauthorized, "no token")
        execute(
            Request.Builder().url("$url/api/me")
                .header("Authorization", "Bearer $token").get().build()
        ) { body ->
            val json = JSONObject(body)
            Result.Success(MeResponse(
                userName = json.getJSONObject("user").getString("name"),
                deviceName = json.getJSONObject("device").getString("name"),
            ))
        }
    }

    suspend fun sendNotification(sender: String, text: String, messenger: String): Result<Unit> =
        withContext(Dispatchers.IO) {
            val url = settings.serverUrl ?: return@withContext err(Result.ErrorKind.Unknown, "no url")
            val token = settings.deviceToken ?: return@withContext err(Result.ErrorKind.Unauthorized, "no token")
            val form = FormBody.Builder()
                .add("sender", sender).add("text", text)
                .add("messenger_name", messenger).build()
            execute(
                Request.Builder().url("$url/add")
                    .header("Authorization", "Bearer $token").post(form).build()
            ) { _ ->
                Result.Success(Unit)
            }
        }

    private inline fun <T> execute(
        request: Request,
        onSuccess: (String) -> Result<T>,
    ): Result<T> {
        return try {
            http.newCall(request).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                when (resp.code) {
                    in 200..299 -> onSuccess(body)
                    400 -> err(Result.ErrorKind.BadRequest, "bad request")
                    401 -> err(Result.ErrorKind.Unauthorized, "unauthorized")
                    404 -> err(Result.ErrorKind.NotFound, "not found")
                    in 500..599 -> err(Result.ErrorKind.Server, "server $resp")
                    else -> err(Result.ErrorKind.Unknown, "http ${resp.code}")
                }
            }
        } catch (e: IOException) {
            err(Result.ErrorKind.Network, e.message ?: "network")
        } catch (e: Exception) {
            err(Result.ErrorKind.Unknown, e.message ?: "unknown")
        }
    }

    private fun <T> err(kind: Result.ErrorKind, msg: String): Result<T> = Result.Error(msg, kind)
}
```

- [ ] **Step 4: Прогон**

```bash
cd android
./gradlew :app:testDebugUnitTest --tests io.skillwood.client.ApiClientTest --no-daemon
```

Ожидается: `5 passed`.

---

### Task 11: `PayloadExtraction` — извлечение полей из StatusBarNotification

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/PayloadExtraction.kt`
- Create: `android/app/src/test/java/io/skillwood/client/PayloadExtractionTest.kt`

- [ ] **Step 1: Падающие тесты**

`android/app/src/test/java/io/skillwood/client/PayloadExtractionTest.kt`:

```kotlin
package io.skillwood.client

import android.app.Notification
import android.os.Bundle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class PayloadExtractionTest {

    private fun bundle(title: String? = null, text: String? = null, bigText: String? = null) =
        Bundle().apply {
            title?.let { putCharSequence(Notification.EXTRA_TITLE, it) }
            text?.let { putCharSequence(Notification.EXTRA_TEXT, it) }
            bigText?.let { putCharSequence(Notification.EXTRA_BIG_TEXT, it) }
        }

    @Test
    fun extracts_when_all_fields_present() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "Привет"),
            appName = "Telegram",
            flags = 0,
        )
        assertNotNull(p)
        assertEquals("Иван", p!!.sender)
        assertEquals("Привет", p.text)
        assertEquals("Telegram", p.messengerName)
    }

    @Test
    fun prefers_big_text_when_present() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "коротко", bigText = "длинно полно"),
            appName = "Telegram",
            flags = 0,
        )
        assertEquals("длинно полно", p!!.text)
    }

    @Test
    fun returns_null_when_title_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "", text = "привет"),
            appName = "Telegram",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun returns_null_when_text_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = ""),
            appName = "Telegram",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun returns_null_when_app_name_blank() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Иван", text = "привет"),
            appName = "",
            flags = 0,
        )
        assertNull(p)
    }

    @Test
    fun skips_ongoing_event() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Музыка", text = "играет"),
            appName = "Spotify",
            flags = Notification.FLAG_ONGOING_EVENT,
        )
        assertNull(p)
    }

    @Test
    fun skips_foreground_service() {
        val p = PayloadExtraction.fromExtras(
            extras = bundle(title = "Сервис", text = "запущен"),
            appName = "AnyApp",
            flags = Notification.FLAG_FOREGROUND_SERVICE,
        )
        assertNull(p)
    }
}
```

- [ ] **Step 2: Реализовать `PayloadExtraction`**

`android/app/src/main/java/io/skillwood/client/PayloadExtraction.kt`:

```kotlin
package io.skillwood.client

import android.app.Notification
import android.os.Bundle

data class Payload(val sender: String, val text: String, val messengerName: String)

object PayloadExtraction {

    fun fromExtras(extras: Bundle, appName: String, flags: Int): Payload? {
        val ongoing = (flags and Notification.FLAG_ONGOING_EVENT) != 0
        val foreground = (flags and Notification.FLAG_FOREGROUND_SERVICE) != 0
        if (ongoing || foreground) return null

        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty().trim()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val plain = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val text = (if (bigText.isNotBlank()) bigText else plain).trim()
        val app = appName.trim()

        if (title.isBlank() || text.isBlank() || app.isBlank()) return null
        return Payload(sender = title, text = text, messengerName = app)
    }
}
```

- [ ] **Step 3: Прогон**

```bash
cd android
./gradlew :app:testDebugUnitTest --tests io.skillwood.client.PayloadExtractionTest --no-daemon
```

Ожидается: `7 passed`.

---

### Task 12: `OutgoingQueue`

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/OutgoingQueue.kt`
- Create: `android/app/src/test/java/io/skillwood/client/OutgoingQueueTest.kt`

- [ ] **Step 1: Падающие тесты**

`android/app/src/test/java/io/skillwood/client/OutgoingQueueTest.kt`:

```kotlin
package io.skillwood.client

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class OutgoingQueueTest {

    private lateinit var q: OutgoingQueue

    @Before
    fun setUp() {
        q = OutgoingQueue(ApplicationProvider.getApplicationContext())
        q.clear()
    }

    @Test
    fun add_and_peek() {
        q.add(Payload("a", "1", "Telegram"))
        q.add(Payload("b", "2", "MAX"))
        val all = q.peekAll()
        assertEquals(2, all.size)
        assertEquals("a", all[0].sender)
        assertEquals("b", all[1].sender)
    }

    @Test
    fun remove_drops_specified_items() {
        val p1 = Payload("a", "1", "Telegram")
        val p2 = Payload("b", "2", "MAX")
        q.add(p1); q.add(p2)
        q.remove(listOf(p1))
        val all = q.peekAll()
        assertEquals(1, all.size)
        assertEquals("b", all[0].sender)
    }

    @Test
    fun fifo_when_overflow() {
        repeat(205) { i ->
            q.add(Payload("s$i", "t$i", "M"))
        }
        val all = q.peekAll()
        assertEquals(200, all.size)
        // Старейшие 5 должны быть выброшены — остались s5..s204
        assertEquals("s5", all.first().sender)
        assertEquals("s204", all.last().sender)
    }

    @Test
    fun roundtrip_serialization_preserves_unicode() {
        q.add(Payload("Иван", "привет 🚀", "Telegram"))
        val parsed = OutgoingQueue(ApplicationProvider.getApplicationContext()).peekAll()
        assertEquals(1, parsed.size)
        assertEquals("Иван", parsed[0].sender)
        assertEquals("привет 🚀", parsed[0].text)
    }
}
```

- [ ] **Step 2: Реализовать `OutgoingQueue`**

`android/app/src/main/java/io/skillwood/client/OutgoingQueue.kt`:

```kotlin
package io.skillwood.client

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class OutgoingQueue(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("skillwood_queue", Context.MODE_PRIVATE)

    fun add(p: Payload) {
        val list = peekAll().toMutableList()
        list.add(p)
        while (list.size > MAX_SIZE) list.removeAt(0)
        save(list)
    }

    fun peekAll(): List<Payload> {
        val raw = prefs.getString(KEY, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map {
                val o = arr.getJSONObject(it)
                Payload(
                    sender = o.getString("sender"),
                    text = o.getString("text"),
                    messengerName = o.getString("messenger"),
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun remove(items: List<Payload>) {
        val toRemove = items.toSet()
        val left = peekAll().filterNot { it in toRemove }
        save(left)
    }

    fun size(): Int = peekAll().size

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    private fun save(list: List<Payload>) {
        val arr = JSONArray()
        list.forEach {
            arr.put(JSONObject(mapOf(
                "sender" to it.sender,
                "text" to it.text,
                "messenger" to it.messengerName,
            )))
        }
        prefs.edit().putString(KEY, arr.toString()).apply()
    }

    companion object {
        private const val KEY = "queue"
        const val MAX_SIZE = 200
    }
}
```

- [ ] **Step 3: Прогон**

```bash
cd android
./gradlew :app:testDebugUnitTest --tests io.skillwood.client.OutgoingQueueTest --no-daemon
```

Ожидается: `4 passed`.

---

## Фаза 4 — Фоновые сервисы и UI

### Task 13: `SkillwoodListener` — слушатель уведомлений

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/SkillwoodListener.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`

> Юнит-тестов нет: компоненты внутри (`PayloadExtraction`, `ApiClient`, `OutgoingQueue`) уже покрыты. Сам сервис — клей. Покрывается smoke-тестом на устройстве в Task 19.

- [ ] **Step 1: Создать `SkillwoodListener.kt`**

```kotlin
package io.skillwood.client

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SkillwoodListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private lateinit var settings: SettingsRepository
    private lateinit var apiClient: ApiClient
    private lateinit var queue: OutgoingQueue

    override fun onCreate() {
        super.onCreate()
        settings = SettingsRepository(this)
        apiClient = ApiClient(settings)
        queue = OutgoingQueue(this)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == applicationContext.packageName) return
        if (!settings.isConfigured()) return

        val appName = try {
            val info = packageManager.getApplicationInfo(sbn.packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (_: Exception) {
            sbn.packageName
        }

        val payload = PayloadExtraction.fromExtras(
            extras = sbn.notification.extras,
            appName = appName,
            flags = sbn.notification.flags,
        ) ?: return

        scope.launch { sendOrEnqueue(payload) }
    }

    private suspend fun sendOrEnqueue(p: Payload) {
        when (val r = apiClient.sendNotification(p.sender, p.text, p.messengerName)) {
            is Result.Success -> {
                settings.recordSuccess()
                broadcastStats()
                drainQueue()
            }
            is Result.Error -> when (r.kind) {
                Result.ErrorKind.Network, Result.ErrorKind.Server, Result.ErrorKind.Unknown -> {
                    queue.add(p)
                    settings.recordError()
                    broadcastStats()
                }
                Result.ErrorKind.Unauthorized -> {
                    settings.clear()
                    sendBroadcast(Intent(ACTION_LOGOUT))
                }
                Result.ErrorKind.BadRequest, Result.ErrorKind.NotFound -> {
                    settings.recordError()
                    broadcastStats()
                }
            }
        }
    }

    private suspend fun drainQueue() {
        val pending = queue.peekAll()
        if (pending.isEmpty()) return
        val sent = mutableListOf<Payload>()
        for (p in pending) {
            val r = apiClient.sendNotification(p.sender, p.text, p.messengerName)
            if (r is Result.Success) {
                sent.add(p); settings.recordSuccess()
            } else break
        }
        if (sent.isNotEmpty()) {
            queue.remove(sent)
            broadcastStats()
        }
    }

    private fun broadcastStats() {
        sendBroadcast(Intent(ACTION_STATS).setPackage(packageName))
    }

    companion object {
        const val ACTION_STATS = "io.skillwood.client.STATS"
        const val ACTION_LOGOUT = "io.skillwood.client.LOGOUT"
    }
}
```

- [ ] **Step 2: Зарегистрировать в манифесте**

В `<application>` (рядом, но НЕ внутри других элементов) добавить:

```xml
<service android:name=".SkillwoodListener"
         android:exported="true"
         android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
    <intent-filter>
        <action android:name="android.service.notification.NotificationListenerService"/>
    </intent-filter>
</service>
```

- [ ] **Step 3: Проверить компиляцию**

```bash
cd android
./gradlew :app:compileDebugKotlin --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`.

---

### Task 14: `ForegroundService` — постоянное уведомление

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/ForegroundService.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Создать `ForegroundService.kt`**

```kotlin
package io.skillwood.client

import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.app.Service
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val tap = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val n: Notification = NotificationCompat.Builder(this, SkillwoodApp.CHANNEL_FOREGROUND)
            .setContentTitle(getString(R.string.foreground_title))
            .setContentText(getString(R.string.foreground_text))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .setContentIntent(tap)
            .build()
        startForeground(NOTIFICATION_ID, n)
        return START_STICKY
    }

    companion object {
        private const val NOTIFICATION_ID = 1001
        fun start(ctx: Context) {
            val i = Intent(ctx, ForegroundService::class.java)
            ctx.startForegroundService(i)
        }
        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, ForegroundService::class.java))
        }
    }
}
```

- [ ] **Step 2: Зарегистрировать в манифесте**

В `<application>` добавить:

```xml
<service android:name=".ForegroundService"
         android:foregroundServiceType="dataSync"
         android:exported="false"/>
```

- [ ] **Step 3: Прогон компиляции**

```bash
cd android
./gradlew :app:compileDebugKotlin --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`.

---

### Task 15: `BootReceiver` — стартует сервис после ребута

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/BootReceiver.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Создать `BootReceiver.kt`**

```kotlin
package io.skillwood.client

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val settings = SettingsRepository(context)
        if (!settings.isConfigured()) return
        ForegroundService.start(context)
    }
}
```

- [ ] **Step 2: Зарегистрировать в манифесте**

В `<application>` добавить:

```xml
<receiver android:name=".BootReceiver" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED"/>
    </intent-filter>
</receiver>
```

- [ ] **Step 3: Компиляция**

```bash
cd android
./gradlew :app:compileDebugKotlin --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`.

---

### Task 16: `MainActivity` и UI

**Files:**
- Create: `android/app/src/main/res/layout/activity_main.xml`
- Create: `android/app/src/main/java/io/skillwood/client/MainActivity.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Layout**

`android/app/src/main/res/layout/activity_main.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<ScrollView xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:padding="20dp">

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical">

        <!-- Состояние "Не настроен" -->
        <LinearLayout
            android:id="@+id/setup_block"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:visibility="visible">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/state_setup_title"
                android:textSize="22sp"
                android:textStyle="bold"
                android:layout_marginBottom="6dp"/>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/state_setup_desc"
                android:textColor="@color/skillwood_neutral"
                android:layout_marginBottom="20dp"/>

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/hint_server_url">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/input_server"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:inputType="textUri"/>
            </com.google.android.material.textfield.TextInputLayout>

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/hint_connect_code">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/input_code"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:inputType="number"
                    android:maxLength="8"/>
            </com.google.android.material.textfield.TextInputLayout>

            <com.google.android.material.textfield.TextInputLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:hint="@string/hint_device_name">
                <com.google.android.material.textfield.TextInputEditText
                    android:id="@+id/input_device_name"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"/>
            </com.google.android.material.textfield.TextInputLayout>

            <com.google.android.material.button.MaterialButton
                android:id="@+id/btn_connect"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/action_connect"
                android:layout_marginTop="12dp"/>

            <TextView
                android:id="@+id/setup_error"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textColor="@color/skillwood_danger"
                android:layout_marginTop="8dp"
                android:visibility="gone"/>
        </LinearLayout>

        <!-- Состояние "Нет доступа" -->
        <LinearLayout
            android:id="@+id/no_access_block"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:visibility="gone">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/state_no_access_title"
                android:textSize="22sp"
                android:textStyle="bold"
                android:layout_marginBottom="6dp"/>

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/state_no_access_desc"
                android:textColor="@color/skillwood_neutral"
                android:layout_marginBottom="20dp"/>

            <com.google.android.material.button.MaterialButton
                android:id="@+id/btn_grant_access"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/action_grant_access"/>
        </LinearLayout>

        <!-- Состояние "Активно" -->
        <LinearLayout
            android:id="@+id/active_block"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:visibility="gone">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:text="@string/state_active_title"
                android:textSize="22sp"
                android:textStyle="bold"
                android:textColor="@color/skillwood_success"
                android:layout_marginBottom="6dp"/>

            <TextView
                android:id="@+id/active_account"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:textColor="@color/skillwood_neutral"
                android:layout_marginBottom="20dp"/>

            <TextView
                android:id="@+id/stat_sent"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginBottom="4dp"/>

            <TextView
                android:id="@+id/stat_last"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginBottom="4dp"/>

            <TextView
                android:id="@+id/stat_errors"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginBottom="4dp"/>

            <TextView
                android:id="@+id/stat_queue"
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginBottom="20dp"/>

            <com.google.android.material.button.MaterialButton
                android:id="@+id/btn_test"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/action_test"
                android:layout_marginBottom="12dp"/>

            <com.google.android.material.button.MaterialButton
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:id="@+id/btn_disconnect"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="@string/action_disconnect"/>
        </LinearLayout>
    </LinearLayout>
</ScrollView>
```

- [ ] **Step 2: `MainActivity.kt`**

`android/app/src/main/java/io/skillwood/client/MainActivity.kt`:

```kotlin
package io.skillwood.client

import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var settings: SettingsRepository
    private lateinit var queue: OutgoingQueue
    private lateinit var apiClient: ApiClient

    private lateinit var setupBlock: View
    private lateinit var noAccessBlock: View
    private lateinit var activeBlock: View

    private lateinit var inputServer: TextInputEditText
    private lateinit var inputCode: TextInputEditText
    private lateinit var inputDeviceName: TextInputEditText
    private lateinit var setupError: TextView

    private lateinit var activeAccount: TextView
    private lateinit var statSent: TextView
    private lateinit var statLast: TextView
    private lateinit var statErrors: TextView
    private lateinit var statQueue: TextView

    private val scope = CoroutineScope(Dispatchers.Main)
    private val dateFormat = SimpleDateFormat("HH:mm", Locale.getDefault())

    private val statsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) { renderStats() }
    }

    private val logoutReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            ForegroundService.stop(this@MainActivity)
            renderState()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = SettingsRepository(this)
        queue = OutgoingQueue(this)
        apiClient = ApiClient(settings)

        setupBlock = findViewById(R.id.setup_block)
        noAccessBlock = findViewById(R.id.no_access_block)
        activeBlock = findViewById(R.id.active_block)

        inputServer = findViewById(R.id.input_server)
        inputCode = findViewById(R.id.input_code)
        inputDeviceName = findViewById(R.id.input_device_name)
        setupError = findViewById(R.id.setup_error)

        activeAccount = findViewById(R.id.active_account)
        statSent = findViewById(R.id.stat_sent)
        statLast = findViewById(R.id.stat_last)
        statErrors = findViewById(R.id.stat_errors)
        statQueue = findViewById(R.id.stat_queue)

        inputServer.setText(settings.serverUrl.orEmpty())
        inputDeviceName.setText(settings.deviceName ?: "${Build.MANUFACTURER} ${Build.MODEL}")

        findViewById<MaterialButton>(R.id.btn_connect).setOnClickListener { onConnect() }
        findViewById<MaterialButton>(R.id.btn_grant_access).setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        findViewById<MaterialButton>(R.id.btn_test).setOnClickListener { onTest() }
        findViewById<MaterialButton>(R.id.btn_disconnect).setOnClickListener { onDisconnect() }
    }

    override fun onResume() {
        super.onResume()
        androidx.core.content.ContextCompat.registerReceiver(
            this, statsReceiver,
            IntentFilter(SkillwoodListener.ACTION_STATS),
            androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        androidx.core.content.ContextCompat.registerReceiver(
            this, logoutReceiver,
            IntentFilter(SkillwoodListener.ACTION_LOGOUT),
            androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        renderState()
    }

    override fun onPause() {
        super.onPause()
        unregisterReceiver(statsReceiver)
        unregisterReceiver(logoutReceiver)
    }

    private fun renderState() {
        when {
            !settings.isConfigured() -> showOnly(setupBlock)
            !isNotificationListenerEnabled() -> showOnly(noAccessBlock)
            else -> { showOnly(activeBlock); ForegroundService.start(this); renderStats() }
        }
    }

    private fun showOnly(block: View) {
        setupBlock.visibility = if (block === setupBlock) View.VISIBLE else View.GONE
        noAccessBlock.visibility = if (block === noAccessBlock) View.VISIBLE else View.GONE
        activeBlock.visibility = if (block === activeBlock) View.VISIBLE else View.GONE
    }

    private fun renderStats() {
        activeAccount.text = getString(R.string.state_active_account, settings.userName ?: "—")
        statSent.text = getString(R.string.stat_sent, settings.sent.toInt())
        statLast.text = getString(
            R.string.stat_last,
            if (settings.lastSentAt > 0) dateFormat.format(Date(settings.lastSentAt)) else "—",
        )
        statErrors.text = getString(R.string.stat_errors, settings.errorsStreak)
        statQueue.text = getString(R.string.stat_queue, queue.size())
    }

    private fun isNotificationListenerEnabled(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: ""
        val cn = ComponentName(this, SkillwoodListener::class.java).flattenToString()
        return enabled.split(":").any { it == cn }
    }

    private fun onConnect() {
        val url = inputServer.text?.toString().orEmpty().trim().trimEnd('/')
        val code = inputCode.text?.toString().orEmpty().trim()
        val name = inputDeviceName.text?.toString().orEmpty().trim()
        if (url.isEmpty() || code.isEmpty() || name.isEmpty()) {
            setupError.text = "Заполните все поля"
            setupError.visibility = View.VISIBLE
            return
        }
        setupError.visibility = View.GONE
        scope.launch {
            val result = withContext(Dispatchers.IO) { apiClient.connect(url, code, name) }
            when (result) {
                is Result.Success -> {
                    settings.serverUrl = url
                    settings.deviceToken = result.value.token
                    settings.userName = result.value.userName
                    settings.deviceName = result.value.deviceName
                    renderState()
                }
                is Result.Error -> {
                    setupError.text = errorMessage(result.kind)
                    setupError.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun onTest() {
        scope.launch {
            withContext(Dispatchers.IO) {
                apiClient.sendNotification(
                    getString(R.string.test_sender),
                    getString(R.string.test_text),
                    getString(R.string.test_messenger),
                )
            }
            settings.recordSuccess()
            renderStats()
        }
    }

    private fun onDisconnect() {
        settings.clear()
        ForegroundService.stop(this)
        renderState()
    }

    private fun errorMessage(kind: Result.ErrorKind): String = when (kind) {
        Result.ErrorKind.Network -> getString(R.string.error_network)
        Result.ErrorKind.NotFound -> getString(R.string.error_unknown_code)
        Result.ErrorKind.Unauthorized -> getString(R.string.error_unauthorized)
        Result.ErrorKind.Server -> getString(R.string.error_server)
        else -> getString(R.string.error_unknown)
    }
}
```

- [ ] **Step 3: Зарегистрировать `MainActivity` в манифесте**

В `<application>` добавить:

```xml
<activity android:name=".MainActivity"
          android:exported="true"
          android:label="@string/app_name">
    <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
    </intent-filter>
</activity>
```

- [ ] **Step 4: Прогон**

```bash
cd android
./gradlew :app:assembleDebug --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`. APK будет в `app/build/outputs/apk/debug/app-debug.apk`.

---

### Task 17: `QueueDrainWorker` — периодический сброс очереди

**Files:**
- Create: `android/app/src/main/java/io/skillwood/client/QueueDrainWorker.kt`
- Modify: `android/app/src/main/java/io/skillwood/client/SkillwoodApp.kt`

- [ ] **Step 1: Создать Worker**

`android/app/src/main/java/io/skillwood/client/QueueDrainWorker.kt`:

```kotlin
package io.skillwood.client

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

class QueueDrainWorker(ctx: Context, params: WorkerParameters)
    : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val settings = SettingsRepository(applicationContext)
        if (!settings.isConfigured()) return Result.success()
        val queue = OutgoingQueue(applicationContext)
        val pending = queue.peekAll()
        if (pending.isEmpty()) return Result.success()

        val client = ApiClient(settings)
        val sent = mutableListOf<Payload>()
        for (p in pending) {
            val r = client.sendNotification(p.sender, p.text, p.messengerName)
            if (r is io.skillwood.client.Result.Success) {
                sent.add(p); settings.recordSuccess()
            } else {
                break
            }
        }
        if (sent.isNotEmpty()) queue.remove(sent)
        return Result.success()
    }
}
```

- [ ] **Step 2: Запустить periodic-задачу из `SkillwoodApp.onCreate`**

Заменить содержимое `SkillwoodApp.kt`:

```kotlin
package io.skillwood.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class SkillwoodApp : Application() {
    override fun onCreate() {
        super.onCreate()
        ensureNotificationChannel()
        scheduleQueueDrain()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(
            CHANNEL_FOREGROUND,
            getString(R.string.channel_foreground),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.channel_foreground_desc)
            setShowBadge(false)
        }
        nm.createNotificationChannel(ch)
    }

    private fun scheduleQueueDrain() {
        val req = PeriodicWorkRequestBuilder<QueueDrainWorker>(15, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "skillwood-queue-drain",
            ExistingPeriodicWorkPolicy.KEEP,
            req,
        )
    }

    companion object {
        const val CHANNEL_FOREGROUND = "skillwood_foreground"
    }
}
```

ВНИМАНИЕ: 15 минут — минимальный интервал WorkManager (Android устанавливает этот лимит). Это не «30 секунд» из спека — мы согласовываем с реальностью платформы. Очередь также сливается прямо в `SkillwoodListener.drainQueue()` после каждого успешного запроса, так что ручной триггер по новому уведомлению остаётся.

- [ ] **Step 3: Прогон сборки**

```bash
cd android
./gradlew :app:assembleDebug --no-daemon
```

Ожидается: `BUILD SUCCESSFUL`.

- [ ] **Step 4: Прогон всех тестов Android**

```bash
cd android
./gradlew :app:testDebugUnitTest --no-daemon
```

Ожидается: все ранее написанные тесты (`SettingsRepositoryTest`, `ApiClientTest`, `PayloadExtractionTest`, `OutgoingQueueTest`) — passed.

---

## Фаза 5 — Сборка и публикация

### Task 18: Скрипт сборки APK и публикация в `dist/`

**Files:**
- Create: `scripts/build_apk.sh`
- Modify: `.git/info/exclude` или корневой `.gitignore`

- [ ] **Step 1: Создать скрипт сборки**

`scripts/build_apk.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d android ]; then
    echo "Папки android/ нет — что-то не так." >&2
    exit 1
fi

cd android
./gradlew assembleDebug --no-daemon

mkdir -p ../dist
cp app/build/outputs/apk/debug/app-debug.apk ../dist/skillwood.apk

echo "Готово: dist/skillwood.apk ($(du -h ../dist/skillwood.apk | cut -f1))"
```

- [ ] **Step 2: Сделать его исполняемым**

```bash
chmod +x scripts/build_apk.sh
```

(на Windows этот шаг не нужен — bash в git for windows игнорирует chmod, но это не вредит).

- [ ] **Step 3: Запустить и проверить**

```bash
./scripts/build_apk.sh
```

Ожидается: `Готово: dist/skillwood.apk` + размер ~5-7 МБ.

- [ ] **Step 4: Проверить раздачу через Flask**

В одной консоли:
```bash
.venv/Scripts/python main.py
```

В другой:
```bash
curl -I http://localhost:5000/download/skillwood.apk
```

Ожидается: `HTTP/1.1 200 OK` и `Content-Type: application/vnd.android.package-archive`.

- [ ] **Step 5: Прогон серверных тестов**

```bash
.venv/Scripts/pytest
```

Все ранее зелёные тесты + новые (~80) должны проходить.

---

### Task 19: Smoke-test на реальном устройстве

> Это ручной шаг — автоматизировать без эмулятора нельзя.

- [ ] **Step 1: Скопировать APK на планшет**

Через USB-кабель (`adb push dist/skillwood.apk /sdcard/Download/skillwood.apk`), Telegram-«Saved Messages», или скачать прямо с `http://<server>:5000/download/skillwood.apk` с браузера планшета.

- [ ] **Step 2: Установить APK**

В файловом менеджере планшета — тапнуть на скачанный `skillwood.apk`. Android попросит разрешить установку из неизвестных источников — разрешить.

- [ ] **Step 3: Открыть Skillwood-клиент и подключить**

1. Открыть приложение Skillwood.
2. Ввести URL сервера (например, `http://192.168.1.3:5000`).
3. Ввести connect_code (берётся с веб-страницы `/code`).
4. Имя устройства (предзаполнено моделью — оставить как есть или поменять).
5. Тап «Подключить».
6. Если успех — появится экран «Нет доступа к уведомлениям».
7. Тап «Дать доступ» → системный экран → переключить Skillwood в положение «вкл» → вернуться в приложение.
8. Должен появиться зелёный «Skillwood активен • Аккаунт: …».

- [ ] **Step 4: Тест — кнопка «Отправить тест»**

- В клиенте тап «Отправить тест».
- На сервере в `/admin/test` или `/contacts` должно появиться сообщение от «Тест» с текстом «Привет от Skillwood-клиента» в мессенджере «Skillwood Test».

- [ ] **Step 5: Тест — реальное уведомление**

- На том же планшете попроси кого-нибудь написать тебе в Telegram (или используй другое устройство для отправки).
- В шторке появится уведомление.
- В Skillwood-веб на странице `/contacts` должно прийти сообщение в течение 1-2 секунд.

- [ ] **Step 6: Тест — ребут планшета**

- Перезагрузить планшет.
- Подождать 30 секунд после загрузки.
- Прислать тестовое уведомление.
- Сообщение должно прийти в Skillwood (BootReceiver поднял ForegroundService, NotificationListener Android поднял сам).

---

## Сводка тестов

После выполнения плана набор тестов:

**Серверные (pytest):**
- `tests/test_devices_model.py` — 3 теста модели Device.
- `tests/test_devices_token.py` — 5 тестов хелперов токена.
- `tests/test_api_connect.py` — 5 тестов `/api/connect`.
- `tests/test_api_me.py` — 4 теста `/api/me`.
- `tests/test_add_bearer.py` — 4 теста двухрежимного `/add`.
- `tests/test_download.py` — 3 теста раздачи APK.
- `tests/test_download_links.py` — 2 теста ссылок в `/home` и `/code`.

Итого: **~26 новых серверных тестов** + 65 существующих = ~91.

**Android (JUnit + Robolectric):**
- `SettingsRepositoryTest` — 5 тестов.
- `ApiClientTest` — 5 тестов.
- `PayloadExtractionTest` — 7 тестов.
- `OutgoingQueueTest` — 4 теста.

Итого: **21 Android-юнит-тест**.
