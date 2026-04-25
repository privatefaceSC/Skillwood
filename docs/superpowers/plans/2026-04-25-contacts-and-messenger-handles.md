# План имплементации: контакты и связывание личностей из мессенджеров

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить плоскую ленту сообщений в контакт-центричную модель: `Contact ← MessengerHandle ← Messages`, с UI «список контактов слева / переписка справа», ручным управлением связями и автоподсказками слияния по похожим именам.

**Architecture:** Новые SQLAlchemy-модели поверх существующего SQLite. `POST /add` ищет/создаёт `MessengerHandle` для пары `(user, messenger, sender)` и привязывает сообщение. Похожесть имён — `difflib.SequenceMatcher.ratio()` поверх нормализованной строки, порог `0.7`, без новых зависимостей. UI на Bootstrap 5 + Jinja, наследует существующий `base.html`.

**Tech Stack:** Python 3.13, Flask 3.1, SQLAlchemy 2.0, sqlalchemy-serializer, Werkzeug, Jinja2, Bootstrap 5 (CDN), pytest (новая зависимость), `difflib` / `re` (stdlib).

**Reference:** [docs/superpowers/specs/2026-04-25-contacts-and-messenger-handles-design.md](../specs/2026-04-25-contacts-and-messenger-handles-design.md)

---

## Фаза 1 — Инфраструктура тестов и тестируемость приложения

### Task 1: Установка pytest и стартовый смок-тест

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Установить pytest в venv**

Запустить (из `d:/ivan/Skillwood`):

```bash
.venv/Scripts/pip install pytest
```

Ожидаемо: `Successfully installed pytest-X.Y.Z` (плюс зависимости).

- [ ] **Step 2: Создать `requirements.txt` с фиксированными версиями**

Запустить:

```bash
.venv/Scripts/pip freeze | grep -iE "^(flask|flask-login|flask-wtf|sqlalchemy|sqlalchemy-serializer|werkzeug|wtforms|pytest|requests)==" > requirements.txt
```

Открыть и проверить, что в файле есть строки вида:

```
Flask==3.1.3
Flask-Login==0.6.3
Flask-WTF==1.2.2
pytest==X.Y.Z
SQLAlchemy==2.0.49
SQLAlchemy-serializer==1.6.3
Werkzeug==3.1.8
WTForms==3.2.1
requests==2.33.1
```

(точные версии не важны — важно, что файл отражает реальные установленные пакеты).

- [ ] **Step 3: Создать пустой `tests/__init__.py`**

```python
```

(пустой файл, чтобы pytest распознал пакет).

- [ ] **Step 4: Добавить `_reset_for_tests` в `data/db_sessions.py`**

ПОЯСНЕНИЕ: переменная `__factory` объявлена на уровне модуля. Снаружи её занулить нельзя (Python трактует `db_sessions.__factory` как mangling для класса вызывающего, а не как доступ к переменной модуля). Поэтому добавляем хелпер, который зануляет её изнутри модуля.

В конец [data/db_sessions.py](../../../data/db_sessions.py) добавить:

```python
def _reset_for_tests():
    """Reset module-level factory. Используется только из тестов."""
    global __factory
    __factory = None
```

- [ ] **Step 5: Создать `tests/conftest.py` с фикстурой in-memory БД**

```python
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
```

- [ ] **Step 6: Создать смок-тест в `tests/test_smoke.py`**

```python
from sqlalchemy import text


def test_db_session_works(db_session):
    """Фикстура отдаёт рабочую сессию к in-memory SQLite."""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
```

ВНИМАНИЕ: в SQLAlchemy 2.0 текстовые SQL-запросы обязательно через `text()`, иначе `ArgumentError: Textual SQL expression ... should be explicitly declared as text()`.

- [ ] **Step 7: Запустить тест, убедиться что проходит**

```bash
.venv/Scripts/pytest tests/test_smoke.py -v
```

Ожидается: `1 passed`.

- [ ] **Step 8: Коммит**

```bash
git add requirements.txt data/db_sessions.py tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "Добавлен pytest + фикстура in-memory БД и смок-тест"
```

---

### Task 2: Минимальный рефактор `main.py` под per-request сессию

Сейчас в `main.py:18` создаётся одна глобальная `db_sess` на всё приложение, и она же привязана к `db/blogs.db` через `global_init` на строке 17. Это блокирует тестирование маршрутов через `Flask test client` — фабрика идемпотентна, БД не переключить.

Заменяем на per-request сессию через `flask.g` + `teardown_appcontext`. Это узкий фикс ради тестируемости, не общий рефакторинг.

**Files:**
- Modify: `main.py`
- Create: `tests/test_app_factory.py`

- [ ] **Step 1: Написать падающий тест на `create_app(":memory:")`**

`tests/test_app_factory.py`:

```python
def test_create_app_returns_flask_app():
    from main import create_app
    app = create_app(":memory:")
    assert app is not None
    assert app.config['SECRET_KEY']


def test_create_app_root_redirects_to_main_menu():
    from main import create_app
    app = create_app(":memory:")
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'main_menu' in response.data or 'Главная'.encode('utf-8') in response.data
```

- [ ] **Step 2: Запустить тест — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_app_factory.py -v
```

Ожидается: FAIL с `ImportError: cannot import name 'create_app' from 'main'`.

- [ ] **Step 3: Перевести `main.py` на app factory + per-request session**

Полностью переписать [main.py](../../../main.py). Текущий файл — 158 строк, целиком переписываем:

```python
import random
import string
from datetime import datetime

from flask import Flask, g, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from data import db_sessions
from data.users import Messages, User


def create_app(db_path: str = "db/blogs.db") -> Flask:
    db_sessions.global_init(db_path)

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'

    @app.teardown_appcontext
    def _close_db(_exc):
        sess = g.pop('db', None)
        if sess is not None:
            sess.close()

    register_routes(app)
    return app


def get_db():
    if 'db' not in g:
        g.db = db_sessions.create_session()
    return g.db


def register_routes(app: Flask) -> None:

    @app.route('/')
    def main_menu():
        if session.get('user_id'):
            return redirect('/home')
        return render_template('main_menu.html')

    @app.route('/logout')
    def logout():
        session.pop('user_id', None)
        return redirect('/')

    @app.route('/home')
    def index():
        user = get_db().query(User).filter(User.id == session['user_id']).first()
        return render_template('index.html', user=user)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            db = get_db()
            name = request.form.get('name')
            surname = request.form.get('surname')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            sex = request.form.get('sex')

            if password != confirm_password:
                return render_template('register.html', message="Пароли не совпадают")

            if db.query(User).filter(User.email == email).first():
                return render_template('register.html', message="Такой пользователь уже есть")

            user = User(
                name=name,
                surname=surname,
                email=email,
                sex=sex,
                hashed_password=generate_password_hash(password),
            )
            user.connect_code = _generate_code()
            db.add(user)
            db.commit()
            session['user_id'] = user.id
            return redirect('/code')

        return render_template('register.html')

    @app.route('/code')
    def code():
        if not session.get('user_id'):
            return redirect('/login')
        user = get_db().query(User).filter(User.id == session['user_id']).first()
        if user.tablet_ip:
            return redirect('/home')
        return render_template('code.html', code=user.connect_code)

    @app.route('/connect', methods=['GET'])
    def connect_tablet():
        db = get_db()
        code_param = request.args.get('code')
        tablet_ip = request.remote_addr
        print(f"Получен код {code_param} от пользователя с айпи: {tablet_ip}")
        user = db.query(User).filter(User.connect_code == code_param).first()
        if user:
            user.tablet_ip = tablet_ip
            db.commit()
            print(f"Устройство подключёно к пользователю {user.name}")
            return "OK", 200
        print("Неверный код")
        return "Неверный код", 404

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            db = get_db()
            email = request.form.get('email')
            password = request.form.get('password')
            user = db.query(User).filter(User.email == email).first()
            if user and check_password_hash(user.hashed_password, password):
                session['user_id'] = user.id
                return redirect('/home')
            return render_template('login.html', message="Неверный email или пароль")
        return render_template('login.html')

    @app.route('/messages')
    def messages():
        if not session.get('user_id'):
            return redirect('/login')
        db = get_db()
        user_id = session['user_id']
        msgs = db.query(Messages).filter(Messages.user_id == user_id).order_by(Messages.id.desc()).all()
        return render_template('chats.html', messages=msgs)

    @app.route('/add', methods=['POST'])
    def add_message():
        db = get_db()
        sender = request.form.get('sender')
        text_value = request.form.get('text')
        messenger_name = request.form.get('messenger_name')
        tablet_ip = request.remote_addr

        user = db.query(User).filter(User.tablet_ip == tablet_ip).first()
        if not user:
            print(f"Неизвестное устройство с IP: {tablet_ip}")
            return 'OK', 200

        time_now = datetime.now().strftime('%H:%M')
        new_message = Messages(
            sender=sender,
            text=text_value,
            messenger_name=messenger_name,
            time=time_now,
            user_id=user.id,
        )
        db.add(new_message)
        db.commit()
        print(f"из {messenger_name}, Пользователю {user.name}: От {sender} - {text_value}")
        return 'OK', 200


def _generate_code() -> str:
    return ''.join(random.choices(string.digits, k=8))


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=False)
```

ВАЖНО: логика всех существующих маршрутов сохранена 1-в-1, только заменено `db_sess` → `get_db()`. Маршруты `/messages` и `/add` мы перепишем в фазе 2 — пока сохраняем поведение.

- [ ] **Step 4: Запустить тест app factory — должен пройти**

```bash
.venv/Scripts/pytest tests/test_app_factory.py -v
```

Ожидается: `2 passed`.

- [ ] **Step 5: Запустить весь тест-сьют, проверить что ничего не сломалось**

```bash
.venv/Scripts/pytest -v
```

Ожидается: все тесты `passed`.

- [ ] **Step 6: Коммит**

```bash
git add main.py tests/test_app_factory.py
git commit -m "Рефактор main.py на create_app + per-request сессию через flask.g"
```

---

## Фаза 2 — Модели данных и автомэтчинг

### Task 3: Модуль `data/matching.py` — нормализация и сходство

**Files:**
- Create: `data/matching.py`
- Create: `tests/test_matching.py`

- [ ] **Step 1: Написать падающие тесты для `normalize` и `similarity_score`**

`tests/test_matching.py`:

```python
import pytest

from data.matching import MATCH_THRESHOLD, normalize, similarity_score


@pytest.mark.parametrize("raw,expected", [
    ("Иван", "иван"),
    ("  Ivan  ", "ivan"),
    ("Ivan!", "ivan"),
    ("Иван 🚀", "иван"),
    ("ВАНЯ", "ваня"),
    ("Anna-Maria", "annamaria"),
    ("user_42", "user42"),
    ("", ""),
])
def test_normalize_strips_case_whitespace_emoji_punctuation(raw, expected):
    assert normalize(raw) == expected


def test_similarity_score_identical_is_one():
    assert similarity_score("ivan", "ivan") == 1.0


def test_similarity_score_completely_different_is_low():
    assert similarity_score("ivan", "xyz") < 0.3


def test_similarity_score_close_names_above_threshold():
    # "ivanp" vs "ivan" — 0.888...
    assert similarity_score("ivanp", "ivan") >= MATCH_THRESHOLD


def test_similarity_score_unrelated_names_below_threshold():
    assert similarity_score("ivan", "petr") < MATCH_THRESHOLD


def test_match_threshold_is_zero_seven():
    assert MATCH_THRESHOLD == 0.7
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_matching.py -v
```

Ожидается: `ImportError: cannot import name 'normalize' from 'data.matching'`.

- [ ] **Step 3: Реализовать `data/matching.py`**

`data/matching.py`:

```python
import re
import unicodedata
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.7


def normalize(s: str) -> str:
    """Привести имя отправителя к канонической форме для сравнения.

    Lowercase, strip, удаление символов кроме букв и цифр (включая emoji).
    """
    s = s.lower().strip()
    return ''.join(
        ch for ch in s
        if unicodedata.category(ch).startswith(('L', 'N'))
    )


def similarity_score(a_norm: str, b_norm: str) -> float:
    """Сходство двух уже нормализованных строк, [0.0, 1.0]."""
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()
```

ПОЯСНЕНИЕ: `unicodedata.category(ch)` для буквы возвращает что-то вроде `Lu`/`Ll`/`Lo`, для цифры `Nd`/`Nl`. Категории, начинающиеся с `L` — буквы любого алфавита (кириллица, латиница), `N` — числа. Emoji попадают в категорию `So` (Symbol, other) и отсеиваются.

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_matching.py -v
```

Ожидается: все тесты `passed`.

- [ ] **Step 5: Коммит**

```bash
git add data/matching.py tests/test_matching.py
git commit -m "Добавлены normalize и similarity_score в data/matching.py"
```

---

### Task 4: Модели `Contact`, `MessengerHandle`, `MergeSuggestion`

**Files:**
- Create: `data/contacts.py`
- Modify: `data/__all_models.py`
- Create: `tests/test_models_contacts.py`

- [ ] **Step 1: Написать падающие тесты на модели**

`tests/test_models_contacts.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from data.contacts import Contact, MergeSuggestion, MessengerHandle
from data.users import User


def _make_user(db, email="u@example.com"):
    user = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def test_create_contact(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    assert contact.id is not None
    assert contact.created_at is not None


def test_create_messenger_handle(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    handle = MessengerHandle(
        contact_id=contact.id,
        user_id=user.id,
        messenger_name="Telegram",
        sender_raw="Иван",
        sender_normalized="иван",
    )
    db_session.add(handle)
    db_session.commit()
    assert handle.id is not None


def test_messenger_handle_unique_constraint(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    h1 = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(h1)
    db_session.commit()
    h2 = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(h2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_merge_suggestion(db_session):
    user = _make_user(db_session)
    c1 = Contact(user_id=user.id, display_name="A")
    c2 = Contact(user_id=user.id, display_name="B")
    db_session.add_all([c1, c2])
    db_session.commit()
    h = MessengerHandle(
        contact_id=c1.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="A", sender_normalized="a",
    )
    db_session.add(h)
    db_session.commit()
    sug = MergeSuggestion(
        user_id=user.id,
        source_handle_id=h.id,
        target_contact_id=c2.id,
        score=0.9,
        status="pending",
    )
    db_session.add(sug)
    db_session.commit()
    assert sug.id is not None


def test_merge_suggestion_unique_constraint(db_session):
    user = _make_user(db_session)
    c1 = Contact(user_id=user.id, display_name="A")
    c2 = Contact(user_id=user.id, display_name="B")
    db_session.add_all([c1, c2])
    db_session.commit()
    h = MessengerHandle(
        contact_id=c1.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="A", sender_normalized="a",
    )
    db_session.add(h)
    db_session.commit()
    s1 = MergeSuggestion(user_id=user.id, source_handle_id=h.id,
                        target_contact_id=c2.id, score=0.9, status="pending")
    db_session.add(s1)
    db_session.commit()
    s2 = MergeSuggestion(user_id=user.id, source_handle_id=h.id,
                        target_contact_id=c2.id, score=0.95, status="pending")
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_models_contacts.py -v
```

Ожидается: `ModuleNotFoundError: No module named 'data.contacts'`.

- [ ] **Step 3: Создать `data/contacts.py`**

```python
import datetime

import sqlalchemy

from .db_sessions import SqlAlchemyBase


class Contact(SqlAlchemyBase):
    __tablename__ = 'contacts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    display_name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)


class MessengerHandle(SqlAlchemyBase):
    __tablename__ = 'messenger_handles'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    contact_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contacts.id"), nullable=False)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    messenger_name = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    sender_raw = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    sender_normalized = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('user_id', 'messenger_name', 'sender_raw',
                                    name='uq_handle_user_messenger_sender'),
    )


class MergeSuggestion(SqlAlchemyBase):
    __tablename__ = 'merge_suggestions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=False)
    source_handle_id = sqlalchemy.Column(sqlalchemy.Integer,
                                         sqlalchemy.ForeignKey("messenger_handles.id"), nullable=False)
    target_contact_id = sqlalchemy.Column(sqlalchemy.Integer,
                                          sqlalchemy.ForeignKey("contacts.id"), nullable=False)
    score = sqlalchemy.Column(sqlalchemy.Float, nullable=False)
    status = sqlalchemy.Column(sqlalchemy.String, nullable=False, default="pending")
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        sqlalchemy.UniqueConstraint('source_handle_id', 'target_contact_id',
                                    name='uq_suggestion_handle_contact'),
    )
```

- [ ] **Step 4: Зарегистрировать модели в `data/__all_models.py`**

Заменить содержимое [data/__all_models.py](../../../data/__all_models.py):

```python
from . import users
from . import contacts
```

- [ ] **Step 5: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_models_contacts.py -v
```

Ожидается: `5 passed`.

- [ ] **Step 6: Коммит**

```bash
git add data/contacts.py data/__all_models.py tests/test_models_contacts.py
git commit -m "Добавлены модели Contact, MessengerHandle, MergeSuggestion"
```

---

### Task 5: Поля `handle_id` и `created_at` у `Messages`

**Files:**
- Modify: `data/users.py`
- Create: `tests/test_messages_new_fields.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_messages_new_fields.py`:

```python
from datetime import datetime

from data.contacts import Contact, MessengerHandle
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_message_has_handle_id_and_created_at(db_session):
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    handle = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван",
    )
    db_session.add(handle)
    db_session.commit()

    now = datetime.now()
    msg = Messages(
        sender="Иван", text="привет", messenger_name="Telegram",
        time=now.strftime("%H:%M"), user_id=user.id,
        handle_id=handle.id, created_at=now,
    )
    db_session.add(msg)
    db_session.commit()
    assert msg.id is not None
    assert msg.handle_id == handle.id
    assert msg.created_at == now


def test_message_handle_id_can_be_null_for_legacy(db_session):
    user = _make_user(db_session)
    msg = Messages(
        sender="Иван", text="привет", messenger_name="Telegram",
        time="10:00", user_id=user.id,
    )
    db_session.add(msg)
    db_session.commit()
    assert msg.id is not None
    assert msg.handle_id is None
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_messages_new_fields.py -v
```

Ожидается: FAIL — у `Messages` нет поля `handle_id` или `created_at`.

- [ ] **Step 3: Добавить поля в `data/users.py` и удалить закомм. Chats**

Полностью переписать [data/users.py](../../../data/users.py):

```python
import datetime

import sqlalchemy

from .db_sessions import SqlAlchemyBase


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    surname = sqlalchemy.Column(sqlalchemy.String)
    name = sqlalchemy.Column(sqlalchemy.String)
    sex = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    email = sqlalchemy.Column(sqlalchemy.String, unique=True)
    hashed_password = sqlalchemy.Column(sqlalchemy.String)
    modified_date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now)
    tablet_ip = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    connect_code = sqlalchemy.Column(sqlalchemy.String, nullable=True, unique=True)


class Messages(SqlAlchemyBase):
    __tablename__ = 'messages'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    sender = sqlalchemy.Column(sqlalchemy.String)
    text = sqlalchemy.Column(sqlalchemy.String)
    messenger_name = sqlalchemy.Column(sqlalchemy.String)
    time = sqlalchemy.Column(sqlalchemy.String)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"), nullable=True)
    handle_id = sqlalchemy.Column(sqlalchemy.Integer,
                                  sqlalchemy.ForeignKey("messenger_handles.id"), nullable=True)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now, nullable=True)
```

(удалены неиспользуемые импорты `orm`, `werkzeug.security`, `flask_login`, `sqlalchemy_serializer` и закомментированный набросок `Chats`).

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_messages_new_fields.py -v
```

Ожидается: `2 passed`.

- [ ] **Step 5: Полный прогон**

```bash
.venv/Scripts/pytest -v
```

Все тесты `passed`.

- [ ] **Step 6: Коммит**

```bash
git add data/users.py tests/test_messages_new_fields.py
git commit -m "Messages: добавлены handle_id и created_at, удалены неиспользуемые импорты и набросок Chats"
```

---

### Task 6: `suggest_merges_for_handle` в `data/matching.py`

**Files:**
- Modify: `data/matching.py`
- Create: `tests/test_suggestions.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_suggestions.py`:

```python
from data.contacts import Contact, MergeSuggestion, MessengerHandle
from data.matching import suggest_merges_for_handle
from data.users import User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _make_handle(db, user, display_name, messenger_name, sender_raw, sender_normalized):
    contact = Contact(user_id=user.id, display_name=display_name)
    db.add(contact)
    db.commit()
    h = MessengerHandle(
        contact_id=contact.id, user_id=user.id,
        messenger_name=messenger_name, sender_raw=sender_raw,
        sender_normalized=sender_normalized,
    )
    db.add(h)
    db.commit()
    return h


def test_creates_suggestion_for_similar_name(db_session):
    user = _make_user(db_session)
    existing = _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Иванn", "Max", "Иванn", "иванn")

    suggest_merges_for_handle(db_session, new)

    sugs = db_session.query(MergeSuggestion).all()
    assert len(sugs) == 1
    assert sugs[0].source_handle_id == new.id
    assert sugs[0].target_contact_id == existing.contact_id
    assert sugs[0].status == "pending"
    assert sugs[0].score >= 0.7


def test_no_suggestion_for_dissimilar_name(db_session):
    user = _make_user(db_session)
    _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Пётр", "Max", "Пётр", "пётр")

    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_suggestion_against_own_contact(db_session):
    """Handle и кандидат принадлежат одному и тому же контакту → пропускаем."""
    user = _make_user(db_session)
    contact = Contact(user_id=user.id, display_name="Иван")
    db_session.add(contact)
    db_session.commit()
    h1 = MessengerHandle(contact_id=contact.id, user_id=user.id,
                         messenger_name="Telegram", sender_raw="Иван", sender_normalized="иван")
    h2 = MessengerHandle(contact_id=contact.id, user_id=user.id,
                         messenger_name="Max", sender_raw="Иванn", sender_normalized="иванn")
    db_session.add_all([h1, h2])
    db_session.commit()

    suggest_merges_for_handle(db_session, h2)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_suggestion_across_users(db_session):
    user_a = _make_user(db_session, "a@example.com")
    user_b = _make_user(db_session, "b@example.com")
    _make_handle(db_session, user_a, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user_b, "Иван", "Max", "Иван", "иван")

    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 0


def test_no_duplicate_suggestion(db_session):
    user = _make_user(db_session)
    _make_handle(db_session, user, "Иван", "Telegram", "Иван", "иван")
    new = _make_handle(db_session, user, "Иванn", "Max", "Иванn", "иванn")

    suggest_merges_for_handle(db_session, new)
    suggest_merges_for_handle(db_session, new)

    assert db_session.query(MergeSuggestion).count() == 1
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_suggestions.py -v
```

Ожидается: `ImportError: cannot import name 'suggest_merges_for_handle' from 'data.matching'`.

- [ ] **Step 3: Реализовать `suggest_merges_for_handle`**

Дописать в [data/matching.py](../../../data/matching.py):

```python
from sqlalchemy.orm import Session


def suggest_merges_for_handle(db: Session, new_handle) -> int:
    """Создать MergeSuggestion(pending) для каждого существующего handle того же
    user_id с другим contact_id и similarity_score ≥ MATCH_THRESHOLD.

    Возвращает количество созданных предложений.
    """
    from .contacts import MergeSuggestion, MessengerHandle

    candidates = (
        db.query(MessengerHandle)
        .filter(
            MessengerHandle.user_id == new_handle.user_id,
            MessengerHandle.contact_id != new_handle.contact_id,
            MessengerHandle.id != new_handle.id,
        )
        .all()
    )

    created = 0
    for cand in candidates:
        score = similarity_score(new_handle.sender_normalized, cand.sender_normalized)
        if score < MATCH_THRESHOLD:
            continue
        # UNIQUE(source_handle_id, target_contact_id) — проверяем заранее.
        exists = (
            db.query(MergeSuggestion)
            .filter(
                MergeSuggestion.source_handle_id == new_handle.id,
                MergeSuggestion.target_contact_id == cand.contact_id,
            )
            .first()
        )
        if exists:
            continue
        db.add(MergeSuggestion(
            user_id=new_handle.user_id,
            source_handle_id=new_handle.id,
            target_contact_id=cand.contact_id,
            score=score,
            status="pending",
        ))
        created += 1

    if created:
        db.commit()
    return created
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_suggestions.py -v
```

Ожидается: `5 passed`.

- [ ] **Step 5: Коммит**

```bash
git add data/matching.py tests/test_suggestions.py
git commit -m "Добавлена suggest_merges_for_handle: автоподсказки слияния"
```

---

## Фаза 3 — Переписанный `POST /add`

### Task 7: Хелперы `data/contacts.py::find_or_create_handle` и `record_message`

Перед тем как править маршрут — выносим логику в чистые функции, чтобы тестировать без HTTP.

**Files:**
- Modify: `data/contacts.py`
- Create: `tests/test_contacts_service.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_contacts_service.py`:

```python
from data.contacts import (
    Contact,
    MessengerHandle,
    find_or_create_handle,
    record_message,
)
from data.users import Messages, User


def _make_user(db, ip="127.0.0.1", email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email,
             hashed_password="x", tablet_ip=ip)
    db.add(u)
    db.commit()
    return u


def test_find_or_create_handle_new_creates_contact_and_handle(db_session):
    user = _make_user(db_session)
    handle, created = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    assert created is True
    assert handle.id is not None
    assert handle.sender_raw == "Иван"
    assert handle.sender_normalized == "иван"
    contact = db_session.query(Contact).get(handle.contact_id)
    assert contact.display_name == "Иван"


def test_find_or_create_handle_existing_returns_same(db_session):
    user = _make_user(db_session)
    h1, c1 = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    h2, c2 = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    assert c1 is True and c2 is False
    assert h1.id == h2.id
    assert db_session.query(Contact).count() == 1


def test_record_message_links_to_handle(db_session):
    user = _make_user(db_session)
    msg = record_message(db_session, user.id, "Telegram", "Иван", "привет")
    assert msg.id is not None
    assert msg.handle_id is not None
    assert msg.user_id == user.id
    assert msg.text == "привет"
    handle = db_session.query(MessengerHandle).get(msg.handle_id)
    assert handle.sender_raw == "Иван"


def test_record_message_reuses_handle_for_same_sender(db_session):
    user = _make_user(db_session)
    m1 = record_message(db_session, user.id, "Telegram", "Иван", "привет")
    m2 = record_message(db_session, user.id, "Telegram", "Иван", "ещё одно")
    assert m1.handle_id == m2.handle_id
    assert db_session.query(Contact).count() == 1
    assert db_session.query(MessengerHandle).count() == 1
    assert db_session.query(Messages).count() == 2
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_contacts_service.py -v
```

Ожидается: `ImportError`.

- [ ] **Step 3: Реализовать функции в `data/contacts.py`**

Дописать в [data/contacts.py](../../../data/contacts.py):

```python
from datetime import datetime

from .matching import normalize, suggest_merges_for_handle
from .users import Messages


def find_or_create_handle(db, user_id: int, messenger_name: str, sender_raw: str):
    """Возвращает (MessengerHandle, created: bool).

    Если handle для (user_id, messenger_name, sender_raw) уже есть — отдаём его.
    Иначе создаём Contact с display_name=sender_raw и MessengerHandle, запускаем
    suggest_merges_for_handle и возвращаем созданный handle с created=True.
    """
    handle = (
        db.query(MessengerHandle)
        .filter(
            MessengerHandle.user_id == user_id,
            MessengerHandle.messenger_name == messenger_name,
            MessengerHandle.sender_raw == sender_raw,
        )
        .first()
    )
    if handle:
        return handle, False

    contact = Contact(user_id=user_id, display_name=sender_raw)
    db.add(contact)
    db.flush()
    handle = MessengerHandle(
        contact_id=contact.id,
        user_id=user_id,
        messenger_name=messenger_name,
        sender_raw=sender_raw,
        sender_normalized=normalize(sender_raw),
    )
    db.add(handle)
    db.flush()
    suggest_merges_for_handle(db, handle)
    return handle, True


def record_message(db, user_id: int, messenger_name: str, sender_raw: str, text: str) -> "Messages":
    """Сохранить сообщение, найдя/создав соответствующий handle."""
    handle, _ = find_or_create_handle(db, user_id, messenger_name, sender_raw)
    now = datetime.now()
    msg = Messages(
        sender=sender_raw,
        text=text,
        messenger_name=messenger_name,
        time=now.strftime("%H:%M"),
        user_id=user_id,
        handle_id=handle.id,
        created_at=now,
    )
    db.add(msg)
    db.commit()
    return msg
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_contacts_service.py -v
```

Ожидается: `4 passed`.

- [ ] **Step 5: Коммит**

```bash
git add data/contacts.py tests/test_contacts_service.py
git commit -m "Хелперы find_or_create_handle и record_message"
```

---

### Task 8: Переписать маршрут `POST /add`

**Files:**
- Modify: `main.py`
- Create: `tests/test_add_endpoint.py`

- [ ] **Step 1: Написать падающие тесты для `/add`**

`tests/test_add_endpoint.py`:

```python
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
def user_with_device(app):
    """Регистрирует пользователя и привязывает к нему IP 127.0.0.1."""
    db = db_sessions.create_session()
    u = User(name="Test", surname="User", sex="male",
             email="t@e.com", hashed_password="x", tablet_ip="127.0.0.1")
    db.add(u)
    db.commit()
    user_id = u.id
    db.close()
    return user_id


def test_add_creates_contact_and_handle_for_new_sender(client, user_with_device):
    response = client.post('/add', data={
        "sender": "Иван", "text": "привет", "messenger_name": "Telegram",
    })
    assert response.status_code == 200

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 1
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
        msg = db.query(Messages).first()
        assert msg.handle_id is not None
        assert msg.text == "привет"
    finally:
        db.close()


def test_add_reuses_handle_for_repeat_sender(client, user_with_device):
    client.post('/add', data={"sender": "Иван", "text": "1", "messenger_name": "Telegram"})
    client.post('/add', data={"sender": "Иван", "text": "2", "messenger_name": "Telegram"})

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 2
        assert db.query(Contact).count() == 1
        assert db.query(MessengerHandle).count() == 1
    finally:
        db.close()


def test_add_returns_400_for_missing_fields(client, user_with_device):
    response = client.post('/add', data={"sender": "Иван"})  # нет text/messenger_name
    assert response.status_code == 400

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 0
    finally:
        db.close()


def test_add_silently_ignores_unknown_device(client):
    """Пользователя для 127.0.0.1 нет — должен вернуть 200 и ничего не записать."""
    response = client.post('/add', data={
        "sender": "Иван", "text": "привет", "messenger_name": "Telegram",
    })
    assert response.status_code == 200

    db = db_sessions.create_session()
    try:
        assert db.query(Messages).count() == 0
    finally:
        db.close()
```

- [ ] **Step 2: Запустить — убедиться что часть падает**

```bash
.venv/Scripts/pytest tests/test_add_endpoint.py -v
```

Ожидается: тест на 400 падает (текущий `/add` возвращает 200 даже без полей); тест на новый sender падает (Contact/Handle не создаются текущим кодом).

- [ ] **Step 3: Переписать `/add` в `main.py`**

В [main.py](../../../main.py) внутри `register_routes(app)` заменить функцию `add_message` на:

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
        tablet_ip = request.remote_addr
        user = db.query(User).filter(User.tablet_ip == tablet_ip).first()
        if not user:
            print(f"Неизвестное устройство с IP: {tablet_ip}")
            return 'OK', 200

        record_message(db, user.id, messenger_name, sender, text_value)
        print(f"из {messenger_name}, Пользователю {user.name}: От {sender} - {text_value}")
        return 'OK', 200
```

- [ ] **Step 4: Запустить — все тесты `/add` должны пройти**

```bash
.venv/Scripts/pytest tests/test_add_endpoint.py -v
```

Ожидается: `4 passed`.

- [ ] **Step 5: Полный прогон**

```bash
.venv/Scripts/pytest -v
```

Все `passed`.

- [ ] **Step 6: Коммит**

```bash
git add main.py tests/test_add_endpoint.py
git commit -m "POST /add: создание Contact/Handle, валидация полей, привязка через record_message"
```

---

## Фаза 4 — Миграция исторических сообщений

### Task 9: Скрипт `data/migrations.py::migrate_to_contacts_v1`

**Files:**
- Create: `data/migrations.py`
- Create: `tests/test_migration.py`

- [ ] **Step 1: Написать падающий тест миграции**

`tests/test_migration.py`:

```python
from data.contacts import Contact, MessengerHandle
from data.migrations import migrate_to_contacts_v1
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_migration_groups_legacy_messages_by_sender(db_session):
    user = _make_user(db_session)
    # Три сообщения от двух разных sender в двух мессенджерах
    db_session.add_all([
        Messages(sender="Иван", text="1", messenger_name="Telegram", time="10:00", user_id=user.id),
        Messages(sender="Иван", text="2", messenger_name="Telegram", time="10:01", user_id=user.id),
        Messages(sender="Пётр", text="3", messenger_name="Max", time="10:02", user_id=user.id),
    ])
    db_session.commit()

    stats = migrate_to_contacts_v1(db_session)

    assert db_session.query(Contact).count() == 2
    assert db_session.query(MessengerHandle).count() == 2
    assert all(m.handle_id is not None for m in db_session.query(Messages).all())
    assert stats["contacts_created"] == 2
    assert stats["handles_created"] == 2
    assert stats["messages_linked"] == 3


def test_migration_is_idempotent(db_session):
    user = _make_user(db_session)
    db_session.add(Messages(sender="Иван", text="1", messenger_name="Telegram",
                            time="10:00", user_id=user.id))
    db_session.commit()

    migrate_to_contacts_v1(db_session)
    second = migrate_to_contacts_v1(db_session)

    assert db_session.query(Contact).count() == 1
    assert db_session.query(MessengerHandle).count() == 1
    assert second["contacts_created"] == 0
    assert second["handles_created"] == 0


def test_migration_does_not_create_suggestions(db_session):
    """Спек §«Миграция данных»: для исторических данных не запускаем автомэтчинг."""
    from data.contacts import MergeSuggestion
    user = _make_user(db_session)
    db_session.add_all([
        Messages(sender="Иван", text="1", messenger_name="Telegram", time="10:00", user_id=user.id),
        Messages(sender="Иванn", text="2", messenger_name="Max", time="10:01", user_id=user.id),
    ])
    db_session.commit()

    migrate_to_contacts_v1(db_session)

    assert db_session.query(MergeSuggestion).count() == 0
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_migration.py -v
```

Ожидается: `ImportError` из `data.migrations`.

- [ ] **Step 3: Реализовать `data/migrations.py`**

```python
"""Одноразовые миграции данных.

Запуск: `python -m data.migrations`.
"""
from datetime import datetime

from sqlalchemy import distinct

from . import db_sessions
from .contacts import Contact, MessengerHandle
from .matching import normalize
from .users import Messages


def migrate_to_contacts_v1(db) -> dict:
    """Привязать существующие Messages к Contact + MessengerHandle.

    Идемпотентна: повторный вызов не создаёт дубликатов и не трогает уже
    привязанные сообщения. Не запускает автомэтчинг (см. спек).

    Возвращает {"contacts_created": int, "handles_created": int, "messages_linked": int}.
    """
    contacts_created = 0
    handles_created = 0
    messages_linked = 0

    triples = (
        db.query(Messages.user_id, Messages.messenger_name, Messages.sender)
        .filter(Messages.handle_id.is_(None))
        .distinct()
        .all()
    )

    for user_id, messenger_name, sender in triples:
        if user_id is None or sender is None or messenger_name is None:
            continue

        handle = (
            db.query(MessengerHandle)
            .filter(
                MessengerHandle.user_id == user_id,
                MessengerHandle.messenger_name == messenger_name,
                MessengerHandle.sender_raw == sender,
            )
            .first()
        )
        if handle is None:
            contact = Contact(user_id=user_id, display_name=sender)
            db.add(contact)
            db.flush()
            contacts_created += 1
            handle = MessengerHandle(
                contact_id=contact.id,
                user_id=user_id,
                messenger_name=messenger_name,
                sender_raw=sender,
                sender_normalized=normalize(sender),
            )
            db.add(handle)
            db.flush()
            handles_created += 1

        updated = (
            db.query(Messages)
            .filter(
                Messages.handle_id.is_(None),
                Messages.user_id == user_id,
                Messages.messenger_name == messenger_name,
                Messages.sender == sender,
            )
            .update({
                Messages.handle_id: handle.id,
                Messages.created_at: datetime.now(),
            }, synchronize_session=False)
        )
        messages_linked += updated

    db.commit()
    return {
        "contacts_created": contacts_created,
        "handles_created": handles_created,
        "messages_linked": messages_linked,
    }


if __name__ == "__main__":
    db_sessions.global_init("db/blogs.db")
    session = db_sessions.create_session()
    try:
        stats = migrate_to_contacts_v1(session)
        print(f"Миграция завершена: {stats}")
    finally:
        session.close()
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_migration.py -v
```

Ожидается: `3 passed`.

- [ ] **Step 5: Коммит**

```bash
git add data/migrations.py tests/test_migration.py
git commit -m "migrate_to_contacts_v1: привязка исторических Messages к Contact/Handle"
```

---

## Фаза 5 — UI просмотра контактов

### Task 10: Маршруты `/contacts` и `/contacts/<id>` + шаблон

**Files:**
- Modify: `main.py`
- Create: `templates/contacts.html`
- Create: `tests/test_contacts_view.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_contacts_view.py`:

```python
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
             hashed_password="x", tablet_ip="127.0.0.1")
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
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_contacts_view.py -v
```

Ожидается: 404 от `/contacts` (маршрута нет) или возвращает что-то странное.

- [ ] **Step 3: Создать `templates/contacts.html`**

```html
{% extends 'base.html' %}

{% block title %}Контакты{% endblock %}

{% block body %}
<meta http-equiv="refresh" content="5">
<div class="container-fluid mt-3">
  <div class="row">
    <div class="col-md-4 border-end" style="height: 80vh; overflow-y: auto;">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h4>Контакты</h4>
        <a href="/contacts/manage" class="btn btn-sm btn-outline-secondary">Связи</a>
      </div>
      {% if contacts %}
        <div class="list-group">
        {% for c in contacts %}
          <a href="/contacts/{{ c.id }}"
             class="list-group-item list-group-item-action {% if selected and selected.id == c.id %}active{% endif %}">
            {{ c.display_name }}
          </a>
        {% endfor %}
        </div>
      {% else %}
        <p class="text-muted">Контактов пока нет — пришлите первое уведомление с устройства.</p>
      {% endif %}
    </div>
    <div class="col-md-8" style="height: 80vh; overflow-y: auto;">
      {% if selected %}
        <h4>{{ selected.display_name }}</h4>
        {% if messages %}
          {% for m in messages %}
            <div class="card mb-2">
              <div class="card-body py-2 px-3">
                <small class="text-muted">[{{ m.messenger_name }}] {{ m.sender }} · {{ m.time }}</small>
                <div>{{ m.text }}</div>
              </div>
            </div>
          {% endfor %}
        {% else %}
          <p class="text-muted">Нет сообщений.</p>
        {% endif %}
      {% else %}
        <p class="text-muted mt-5 text-center">Выберите контакт слева.</p>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Добавить маршруты в `main.py`**

В [main.py](../../../main.py) внутри `register_routes(app)`:

1. Заменить функцию `messages` на редирект:

```python
    @app.route('/messages')
    def messages():
        return redirect('/contacts')
```

2. Добавить новые маршруты `/contacts` и `/contacts/<int:contact_id>` (после `messages`):

```python
    @app.route('/contacts')
    def contacts_index():
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact
        db = get_db()
        user_id = session['user_id']
        contacts = (
            db.query(Contact)
            .filter(Contact.user_id == user_id)
            .order_by(Contact.display_name.asc())
            .all()
        )
        return render_template('contacts.html', contacts=contacts, selected=None, messages=None)


    @app.route('/contacts/<int:contact_id>')
    def contact_detail(contact_id):
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact, MessengerHandle
        db = get_db()
        user_id = session['user_id']
        contact = (
            db.query(Contact)
            .filter(Contact.id == contact_id, Contact.user_id == user_id)
            .first()
        )
        if not contact:
            return 'Not Found', 404

        contacts = (
            db.query(Contact)
            .filter(Contact.user_id == user_id)
            .order_by(Contact.display_name.asc())
            .all()
        )
        handle_ids = [h.id for h in
                      db.query(MessengerHandle).filter(MessengerHandle.contact_id == contact.id).all()]
        msgs = (
            db.query(Messages)
            .filter(Messages.handle_id.in_(handle_ids))
            .order_by(Messages.created_at.desc().nullslast(), Messages.id.desc())
            .all()
        )
        return render_template('contacts.html', contacts=contacts, selected=contact, messages=msgs)
```

ПОЯСНЕНИЕ: `Messages.created_at.desc().nullslast()` ставит исторические сообщения с `NULL` (до миграции `created_at` могло быть None) в конец. Сортировка по `id desc` как fallback.

- [ ] **Step 5: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_contacts_view.py -v
```

Ожидается: `5 passed`.

- [ ] **Step 6: Полный прогон**

```bash
.venv/Scripts/pytest -v
```

Все `passed`.

- [ ] **Step 7: Коммит**

```bash
git add main.py templates/contacts.html tests/test_contacts_view.py
git commit -m "Маршруты /contacts и /contacts/<id>, шаблон списка контактов и переписки"
```

---

## Фаза 6 — Управление связями

### Task 11: Маршрут `/contacts/manage` и шаблон

**Files:**
- Modify: `main.py`
- Create: `templates/contacts_manage.html`
- Create: `tests/test_contacts_manage.py`

- [ ] **Step 1: Тест на отображение страницы**

`tests/test_contacts_manage.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_contacts_manage.py -v
```

Ожидается: 404 на `/contacts/manage`.

- [ ] **Step 3: Создать шаблон `templates/contacts_manage.html`**

```html
{% extends 'base.html' %}

{% block title %}Управление связями{% endblock %}

{% block body %}
<div class="container mt-3">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h3>Управление связями</h3>
    <a href="/contacts" class="btn btn-outline-secondary">К контактам</a>
  </div>

  {% if suggestions %}
    <h5>Подсказки слияния</h5>
    <p class="text-muted small">Программа предполагает, что это один и тот же человек. Решение — за вами.</p>
    <ul class="list-group mb-4">
      {% for s in suggestions %}
        <li class="list-group-item d-flex justify-content-between align-items-center">
          <span>
            <strong>{{ s.source_handle.sender_raw }}</strong>
            <small class="text-muted">[{{ s.source_handle.messenger_name }}]</small>
            ≈
            <strong>{{ s.target_contact.display_name }}</strong>
            <small class="text-muted">(сходство {{ "%.2f"|format(s.score) }})</small>
          </span>
          <span>
            <form method="post" action="/contacts/suggestions/{{ s.id }}/accept" class="d-inline">
              <button class="btn btn-sm btn-success">Объединить</button>
            </form>
            <form method="post" action="/contacts/suggestions/{{ s.id }}/dismiss" class="d-inline">
              <button class="btn btn-sm btn-outline-secondary">Скрыть</button>
            </form>
          </span>
        </li>
      {% endfor %}
    </ul>
  {% endif %}

  <h5>Личности (handles)</h5>
  <table class="table table-sm">
    <thead><tr><th>Контакт</th><th>Мессенджер</th><th>Имя</th><th></th></tr></thead>
    <tbody>
      {% for h in handles %}
        <tr>
          <td>{{ h.contact.display_name }}</td>
          <td>{{ h.messenger_name }}</td>
          <td>{{ h.sender_raw }}</td>
          <td>
            <form method="post" action="/contacts/handles/{{ h.id }}/move" class="d-inline">
              <select name="target_contact_id" class="form-select form-select-sm d-inline-block" style="width:auto;">
                {% for c in all_contacts %}
                  {% if c.id != h.contact_id %}
                    <option value="{{ c.id }}">{{ c.display_name }}</option>
                  {% endif %}
                {% endfor %}
              </select>
              <button class="btn btn-sm btn-outline-primary">Переместить</button>
            </form>
          </td>
        </tr>
      {% endfor %}
    </tbody>
  </table>

  <h5 class="mt-4">Переименовать контакт</h5>
  <table class="table table-sm">
    <tbody>
      {% for c in all_contacts %}
        <tr>
          <td>
            <form method="post" action="/contacts/{{ c.id }}/rename" class="d-flex">
              <input name="display_name" class="form-control form-control-sm" value="{{ c.display_name }}">
              <button class="btn btn-sm btn-outline-primary ms-2">Сохранить</button>
            </form>
          </td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

ВНИМАНИЕ: шаблон обращается к `s.source_handle`, `s.target_contact`, `h.contact` — это relationship'ы, которых пока нет на моделях. Добавим их в следующем шаге.

- [ ] **Step 4: Добавить relationship'ы в `data/contacts.py`**

В [data/contacts.py](../../../data/contacts.py) добавить импорт `relationship` и поля:

```python
from sqlalchemy import orm
```

В `Contact` — после колонок добавить:

```python
    handles = orm.relationship("MessengerHandle", back_populates="contact",
                               foreign_keys="MessengerHandle.contact_id")
```

В `MessengerHandle` — после колонок:

```python
    contact = orm.relationship("Contact", back_populates="handles", foreign_keys=[contact_id])
```

В `MergeSuggestion` — после колонок:

```python
    source_handle = orm.relationship("MessengerHandle", foreign_keys=[source_handle_id])
    target_contact = orm.relationship("Contact", foreign_keys=[target_contact_id])
```

- [ ] **Step 5: Добавить маршрут `/contacts/manage` в `main.py`**

После `contact_detail`:

```python
    @app.route('/contacts/manage')
    def contacts_manage():
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact, MergeSuggestion, MessengerHandle
        db = get_db()
        user_id = session['user_id']
        all_contacts = (db.query(Contact).filter(Contact.user_id == user_id)
                        .order_by(Contact.display_name.asc()).all())
        handles = (db.query(MessengerHandle).filter(MessengerHandle.user_id == user_id)
                   .order_by(MessengerHandle.messenger_name.asc()).all())
        suggestions = (db.query(MergeSuggestion)
                       .filter(MergeSuggestion.user_id == user_id,
                               MergeSuggestion.status == "pending")
                       .order_by(MergeSuggestion.score.desc()).all())
        return render_template('contacts_manage.html',
                               all_contacts=all_contacts, handles=handles, suggestions=suggestions)
```

- [ ] **Step 6: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_contacts_manage.py -v
```

Ожидается: `2 passed`.

- [ ] **Step 7: Коммит**

```bash
git add main.py data/contacts.py templates/contacts_manage.html tests/test_contacts_manage.py
git commit -m "Страница /contacts/manage: список handles и подсказок слияния"
```

---

### Task 12: POST-маршруты merge / move / rename

**Files:**
- Modify: `main.py`
- Create: `tests/test_merge_actions.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_merge_actions.py`:

```python
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
        c = db.query(Contact).get(c1_id)
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
    # сливаем c1 (source) → c2 (target)
    r = client.post('/contacts/merge', data={"source_id": c1_id, "target_id": c2_id})
    assert r.status_code in (200, 302)

    db = db_sessions.create_session()
    try:
        assert db.query(Contact).filter(Contact.id == c1_id).first() is None
        assert db.query(Contact).filter(Contact.id == c2_id).first() is not None
        h1 = db.query(MessengerHandle).get(h1_id)
        assert h1.contact_id == c2_id  # перепривязан
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
    """При merge висящие предложения, ссылающиеся на удаляемый контакт, помечаются dismissed."""
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
        s = db.query(MergeSuggestion).get(sug_id)
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
        h = db.query(MessengerHandle).get(h1_id)
        assert h.contact_id == c2_id
    finally:
        db.close()
```

- [ ] **Step 2: Запустить — убедиться что падает**

```bash
.venv/Scripts/pytest tests/test_merge_actions.py -v
```

Ожидается: 7 fail (маршрутов нет).

- [ ] **Step 3: Реализовать сервисную функцию `merge_contacts`**

В [data/contacts.py](../../../data/contacts.py) дописать:

```python
def merge_contacts(db, user_id: int, source_id: int, target_id: int) -> None:
    """Переподвязать все handles source-Contact на target и удалить source.

    Помечает dismissed все pending-предложения, ссылающиеся на удаляемый контакт
    (как target) или на любой из его handles (как source_handle).

    Бросает ValueError("same") если source_id == target_id.
    Бросает LookupError если контакты не принадлежат user_id.
    """
    if source_id == target_id:
        raise ValueError("same")
    src = db.query(Contact).filter(Contact.id == source_id, Contact.user_id == user_id).first()
    tgt = db.query(Contact).filter(Contact.id == target_id, Contact.user_id == user_id).first()
    if not src or not tgt:
        raise LookupError()

    src_handle_ids = [h.id for h in
                      db.query(MessengerHandle).filter(MessengerHandle.contact_id == source_id).all()]

    db.query(MessengerHandle).filter(MessengerHandle.contact_id == source_id).update(
        {MessengerHandle.contact_id: target_id}, synchronize_session=False
    )

    db.query(MergeSuggestion).filter(
        MergeSuggestion.status == "pending",
        sqlalchemy.or_(
            MergeSuggestion.target_contact_id == source_id,
            MergeSuggestion.source_handle_id.in_(src_handle_ids) if src_handle_ids else False,
        ),
    ).update({MergeSuggestion.status: "dismissed"}, synchronize_session=False)

    db.delete(src)
    db.commit()
```

ВНИМАНИЕ: добавить `import sqlalchemy` в начало `data/contacts.py` если его нет (он уже есть для определения колонок).

- [ ] **Step 4: Добавить маршруты в `main.py`**

После `contacts_manage`:

```python
    @app.route('/contacts/<int:contact_id>/rename', methods=['POST'])
    def contact_rename(contact_id):
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact
        db = get_db()
        user_id = session['user_id']
        contact = db.query(Contact).filter(
            Contact.id == contact_id, Contact.user_id == user_id).first()
        if not contact:
            return 'Not Found', 404
        new_name = request.form.get('display_name', '').strip()
        if new_name:
            contact.display_name = new_name
            db.commit()
        return redirect('/contacts/manage')


    @app.route('/contacts/merge', methods=['POST'])
    def contacts_merge():
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import merge_contacts
        db = get_db()
        try:
            source_id = int(request.form['source_id'])
            target_id = int(request.form['target_id'])
        except (KeyError, ValueError):
            return 'Bad Request', 400
        try:
            merge_contacts(db, session['user_id'], source_id, target_id)
        except ValueError:
            return 'Bad Request', 400
        except LookupError:
            return 'Not Found', 404
        return redirect('/contacts/manage')


    @app.route('/contacts/handles/<int:handle_id>/move', methods=['POST'])
    def handle_move(handle_id):
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact, MessengerHandle
        db = get_db()
        user_id = session['user_id']
        handle = db.query(MessengerHandle).filter(
            MessengerHandle.id == handle_id, MessengerHandle.user_id == user_id).first()
        if not handle:
            return 'Not Found', 404
        try:
            target_id = int(request.form['target_contact_id'])
        except (KeyError, ValueError):
            return 'Bad Request', 400
        target = db.query(Contact).filter(
            Contact.id == target_id, Contact.user_id == user_id).first()
        if not target:
            return 'Not Found', 404
        handle.contact_id = target_id
        db.commit()
        return redirect('/contacts/manage')
```

- [ ] **Step 5: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_merge_actions.py -v
```

Ожидается: `7 passed`.

- [ ] **Step 6: Коммит**

```bash
git add main.py data/contacts.py tests/test_merge_actions.py
git commit -m "Маршруты rename/merge/handle-move + сервисная merge_contacts"
```

---

### Task 13: Маршруты accept / dismiss подсказок

**Files:**
- Modify: `main.py`
- Create: `tests/test_suggestion_actions.py`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_suggestion_actions.py`:

```python
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
        assert db.query(MergeSuggestion).get(sug_id).status == "dismissed"
    finally:
        db.close()


def test_accept_performs_merge(client, setup_pending_suggestion):
    user_id, c1_id, c2_id, h2_id, sug_id = setup_pending_suggestion
    _login(client, user_id)
    r = client.post(f'/contacts/suggestions/{sug_id}/accept')
    assert r.status_code in (200, 302)
    db = db_sessions.create_session()
    try:
        # source_handle принадлежал c2 (B), target_contact = c1 (A) → c2 должен исчезнуть.
        # source-Contact для merge — это контакт source_handle (c2).
        assert db.query(Contact).get(c2_id) is None
        assert db.query(Contact).get(c1_id) is not None
        h2 = db.query(MessengerHandle).get(h2_id)
        assert h2.contact_id == c1_id
        assert db.query(MergeSuggestion).get(sug_id).status == "accepted"
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
```

- [ ] **Step 2: Запустить — должны падать**

```bash
.venv/Scripts/pytest tests/test_suggestion_actions.py -v
```

Ожидается: 3 fail (маршрутов нет).

- [ ] **Step 3: Реализовать маршруты в `main.py`**

После `handle_move`:

```python
    @app.route('/contacts/suggestions/<int:sug_id>/dismiss', methods=['POST'])
    def suggestion_dismiss(sug_id):
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import MergeSuggestion
        db = get_db()
        sug = db.query(MergeSuggestion).filter(
            MergeSuggestion.id == sug_id,
            MergeSuggestion.user_id == session['user_id']).first()
        if not sug:
            return 'Not Found', 404
        sug.status = "dismissed"
        db.commit()
        return redirect('/contacts/manage')


    @app.route('/contacts/suggestions/<int:sug_id>/accept', methods=['POST'])
    def suggestion_accept(sug_id):
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import MergeSuggestion, MessengerHandle, merge_contacts
        db = get_db()
        user_id = session['user_id']
        sug = db.query(MergeSuggestion).filter(
            MergeSuggestion.id == sug_id, MergeSuggestion.user_id == user_id).first()
        if not sug:
            return 'Not Found', 404
        source_handle = db.query(MessengerHandle).get(sug.source_handle_id)
        try:
            merge_contacts(db, user_id, source_handle.contact_id, sug.target_contact_id)
        except (ValueError, LookupError):
            return 'Conflict', 409
        sug.status = "accepted"
        db.commit()
        return redirect('/contacts/manage')
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
.venv/Scripts/pytest tests/test_suggestion_actions.py -v
```

Ожидается: `3 passed`.

- [ ] **Step 5: Полный прогон**

```bash
.venv/Scripts/pytest -v
```

Все `passed`.

- [ ] **Step 6: Коммит**

```bash
git add main.py tests/test_suggestion_actions.py
git commit -m "Маршруты /contacts/suggestions/<id>/accept и dismiss"
```

---

## Фаза 7 — Финальная сборка

### Task 14: Прогон миграции на реальной БД и обновление `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Сделать резервную копию БД**

```bash
cp d:/ivan/Skillwood/db/blogs.db d:/ivan/Skillwood/db/blogs.db.backup-$(date +%Y%m%d)
```

- [ ] **Step 2: Создать новые таблицы (одного импорта моделей достаточно)**

`SqlAlchemyBase.metadata.create_all(engine)` вызывается внутри `db_sessions.global_init`. Запустим короткий скрипт, чтобы он отработал на реальной БД:

```bash
.venv/Scripts/python -c "from data import db_sessions; db_sessions.global_init('db/blogs.db'); print('tables created')"
```

Ожидается: `Подключение к базе данных по адресу sqlite:///db/blogs.db?check_same_thread=False` и `tables created`. Это создаёт новые таблицы `contacts`, `messenger_handles`, `merge_suggestions`, **но не добавляет колонки** в существующую `messages`.

- [ ] **Step 3: Добавить колонки `handle_id` и `created_at` в `messages` через ALTER TABLE**

`metadata.create_all` не изменяет существующие таблицы — для этого нужен `ALTER TABLE`. Запустим:

```bash
.venv/Scripts/python -c "
import sqlite3
con = sqlite3.connect('db/blogs.db')
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(messages)').fetchall()]
if 'handle_id' not in cols:
    cur.execute('ALTER TABLE messages ADD COLUMN handle_id INTEGER REFERENCES messenger_handles(id)')
if 'created_at' not in cols:
    cur.execute('ALTER TABLE messages ADD COLUMN created_at DATETIME')
con.commit()
con.close()
print('schema updated')
"
```

Ожидается: `schema updated`. Команда идемпотентна — при повторе ничего не изменит.

- [ ] **Step 4: Прогнать миграцию данных**

```bash
.venv/Scripts/python -m data.migrations
```

Ожидается: `Миграция завершена: {'contacts_created': N, 'handles_created': N, 'messages_linked': M}` — где числа отражают реальное состояние БД.

- [ ] **Step 5: Запустить сервер и проверить вручную**

```bash
.venv/Scripts/python main.py
```

В браузере: `http://localhost:5000/login`, войти существующим аккаунтом, открыть `/contacts` — должны увидеть мигрированные контакты, выбрать любой — увидеть переписку. `/contacts/manage` — список handles.

- [ ] **Step 6: Остановить сервер (Ctrl+C)**

- [ ] **Step 7: Обновить `CLAUDE.md`**

Открыть [CLAUDE.md](../../../CLAUDE.md) и заменить раздел `## Архитектура` (всё от строки `## Архитектура` до `## Соглашения, которые стоит сохранять`) на:

```markdown
## Архитектура

Это небольшое Flask-приложение, работающее как **мост между личным Android-устройством (с MacroDroid) и веб-панелью** для просмотра уведомлений из мессенджеров. Интерфейс и тексты — на русском.

### Создание приложения

Точка входа — `create_app(db_path="db/blogs.db")` в [main.py](main.py). Внутри: `db_sessions.global_init(db_path)`, создание Flask-app, регистрация маршрутов, `teardown_appcontext` для закрытия per-request сессии.

### Привязка устройства (центральная нетривиальная идея)

1. Регистрация на `/register` → сервер генерирует 8-значный `connect_code`, сохраняет на `User`.
2. Код показывается на `/code` (auto-refresh 3 секунды).
3. Android-устройство (макрос MacroDroid) делает `GET /connect?code=<код>`. Сервер сохраняет `request.remote_addr` как `User.tablet_ip`.
4. После заполнения `tablet_ip` страница `/code` редиректит на `/home`.
5. Уведомления из мессенджеров шлются через `POST /add` (поля `sender`, `text`, `messenger_name`). Пользователь определяется по совпадению `request.remote_addr` с `User.tablet_ip` — без токена. Стабильность IP в локалке критична.

### Контакт-центричная модель сообщений

Сообщения не валятся в одну ленту, а группируются по контактам:

```
User
 └─ 1:N → Contact(display_name)            ← реальный человек глазами владельца
            └─ 1:N → MessengerHandle       ← конкретная личность в конкретном мессенджере
                       └─ 1:N → Messages   ← сообщение, привязано к handle
```

`POST /add` ищет `MessengerHandle` по `(user_id, messenger_name, sender_raw)`. Не нашёл — создаёт новый `Contact` с `display_name = sender` и привязывает handle. После создания нового handle [data/matching.py](data/matching.py) сравнивает `sender_normalized` с другими handles того же `user_id`: при сходстве ≥ `MATCH_THRESHOLD = 0.7` создаётся `MergeSuggestion(status='pending')` для подсказки в UI.

UI:
- `/contacts` — двухпанельный лейаут (список / переписка).
- `/contacts/<id>` — переписка с контактом, агрегирует сообщения всех его handles.
- `/contacts/manage` — управление связями: переименование, перемещение handle между контактами, объединение контактов, принятие/скрытие подсказок.

Старый `/messages` редиректит на `/contacts`.

### Слой данных

- **SQLite** в `db/blogs.db`. Путь по умолчанию в `create_app("db/blogs.db")`, в тестах — `:memory:`.
- Engine создаётся с `check_same_thread=False`. Сессия теперь **per-request** через `flask.g`: `get_db()` создаёт сессию при первом обращении в обработчике, `teardown_appcontext` закрывает.
- Модели:
  - [data/users.py](data/users.py) — `User`, `Messages`. У `Messages` поля `handle_id` (FK) и `created_at` добавлены под контакты; `sender`/`messenger_name` остаются как исторический снимок.
  - [data/contacts.py](data/contacts.py) — `Contact`, `MessengerHandle`, `MergeSuggestion`, плюс сервисные функции `find_or_create_handle`, `record_message`, `merge_contacts`.
- [data/matching.py](data/matching.py) — `normalize`, `similarity_score`, `MATCH_THRESHOLD`, `suggest_merges_for_handle`. Использует `difflib` (stdlib).
- Новые модели должны импортироваться в [data/__all_models.py](data/__all_models.py).
- `data/db_sessions.py` экспортирует `global_init`, `create_session`, `_reset_for_tests` (последняя — только для pytest-фикстур).

### Миграция исторических данных

[data/migrations.py](data/migrations.py) `migrate_to_contacts_v1` — одноразовый запуск (`python -m data.migrations`). Группирует существующие `Messages` по `(user_id, messenger_name, sender)` и создаёт под каждую группу `Contact + MessengerHandle`. Идемпотентна. Автомэтчинг для исторических данных намеренно не запускается — иначе UI завалится подсказками.

ВАЖНО: для существующей `db/blogs.db` нужно вручную добавить колонки `handle_id` и `created_at` в `messages` через `ALTER TABLE` перед запуском миграции — SQLAlchemy `create_all` не делает ALTER на существующих таблицах.

### Тестирование

Тесты на pytest в `tests/`. Фикстура `db_session` (в [tests/conftest.py](tests/conftest.py)) переинициализирует фабрику на in-memory SQLite через `db_sessions._reset_for_tests()` + `global_init(":memory:")`. Тесты с маршрутами создают приложение через `create_app(":memory:")` и используют `app.test_client()`.

Запуск: `.venv/Scripts/pytest -v`.
```

Дополнительно — в начало раздела "Запуск приложения" заменить блок про "Файла requirements.txt нет" на:

```markdown
Зависимости зафиксированы в `requirements.txt`. Установка после `python -m venv .venv` и активации:

```bash
pip install -r requirements.txt
```

Тесты на pytest в `tests/`. Запуск: `.venv/Scripts/pytest -v`.
```

В разделе "Inactive code" из старого CLAUDE.md удалить упоминание про закомментированный `Chats` (мы его удалили в Task 5).

- [ ] **Step 8: Прогнать все тесты ещё раз**

```bash
.venv/Scripts/pytest -v
```

Все `passed`.

- [ ] **Step 9: Коммит**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: обновлён под контакт-центричную модель и новый процесс тестирования"
```

---

## Сводка по тестам

После завершения плана набор тестов:

| Файл | Что проверяет |
|---|---|
| `tests/test_smoke.py` | Фикстура in-memory БД работает. |
| `tests/test_app_factory.py` | `create_app(":memory:")` отдаёт работающее Flask-приложение. |
| `tests/test_matching.py` | `normalize`, `similarity_score`, `MATCH_THRESHOLD`. |
| `tests/test_models_contacts.py` | Модели `Contact`/`MessengerHandle`/`MergeSuggestion` и UNIQUE constraints. |
| `tests/test_messages_new_fields.py` | `Messages.handle_id`, `Messages.created_at`. |
| `tests/test_suggestions.py` | `suggest_merges_for_handle` создаёт/не создаёт `MergeSuggestion`. |
| `tests/test_contacts_service.py` | `find_or_create_handle`, `record_message`. |
| `tests/test_add_endpoint.py` | `POST /add`: новый sender, повтор, 400 без полей, 200 без устройства. |
| `tests/test_migration.py` | `migrate_to_contacts_v1` группирует, идемпотентна, без подсказок. |
| `tests/test_contacts_view.py` | `/contacts`, `/contacts/<id>`, редирект `/messages`, 404, login required. |
| `tests/test_contacts_manage.py` | `/contacts/manage` рендерит handles и подсказки. |
| `tests/test_merge_actions.py` | rename/merge/handle-move: happy paths, 400, 404, dismiss висящих подсказок. |
| `tests/test_suggestion_actions.py` | `accept`/`dismiss` подсказок, 404 для чужих. |

---

## Сводка по коммитам

1. `Добавлен pytest + фикстура in-memory БД и смок-тест`
2. `Рефактор main.py на create_app + per-request сессию через flask.g`
3. `Добавлены normalize и similarity_score в data/matching.py`
4. `Добавлены модели Contact, MessengerHandle, MergeSuggestion`
5. `Messages: добавлены handle_id и created_at, удалены неиспользуемые импорты и набросок Chats`
6. `Добавлена suggest_merges_for_handle: автоподсказки слияния`
7. `Хелперы find_or_create_handle и record_message`
8. `POST /add: создание Contact/Handle, валидация полей, привязка через record_message`
9. `migrate_to_contacts_v1: привязка исторических Messages к Contact/Handle`
10. `Маршруты /contacts и /contacts/<id>, шаблон списка контактов и переписки`
11. `Страница /contacts/manage: список handles и подсказок слияния`
12. `Маршруты rename/merge/handle-move + сервисная merge_contacts`
13. `Маршруты /contacts/suggestions/<id>/accept и dismiss`
14. `CLAUDE.md: обновлён под контакт-центричную модель и новый процесс тестирования`
