from datetime import datetime

import pytest

from data import db_sessions
from data.contacts import (
    Contact,
    MergeSuggestion,
    MessengerHandle,
    find_or_create_handle,
    record_message,
)
from data.matching import display_author, split_group_sender
from data.migrations import migrate_group_handles_v1
from data.users import Messages, User


def _make_user(db, email="u@example.com"):
    u = User(name="U", surname="S", sex="male", email=email,
             hashed_password="x")
    db.add(u)
    db.commit()
    return u


# ---------- split_group_sender ----------


@pytest.mark.parametrize("raw,expected", [
    ("9б класс: Софья Гоева", ("9б класс", "Софья Гоева")),
    ("9б класс:Софья Гоева", ("9б класс", "Софья Гоева")),
    ("9б класс :  Софья", ("9б класс", "Софья")),
    ("Время: 10:30 PM", ("Время", "10:30 PM")),
])
def test_split_group_sender_parses_prefix(raw, expected):
    assert split_group_sender(raw) == expected


@pytest.mark.parametrize("raw", [
    "Софья",
    ":Софья",
    "Софья:",
    "  :  ",
    "",
    ":",
])
def test_split_group_sender_rejects_invalid(raw):
    assert split_group_sender(raw) is None


# ---------- display_author ----------


def test_display_author_strips_matching_prefix():
    assert display_author("9б класс: Софья", "9б класс") == "Софья"


def test_display_author_strips_when_no_space_after_colon():
    assert display_author("9б класс:Софья", "9б класс") == "Софья"


def test_display_author_keeps_when_prefix_mismatches():
    assert display_author("Doctor:Strange", "Кто-то другой") == "Doctor:Strange"


def test_display_author_keeps_when_no_colon():
    assert display_author("Иван Иванов", "Иван Иванов") == "Иван Иванов"


def test_display_author_handles_empty():
    assert display_author("", "что-то") == ""
    assert display_author("Иван", "") == "Иван"


# ---------- find_or_create_handle: промоушн ----------


def test_first_handle_with_colon_creates_singleton_contact(db_session):
    user = _make_user(db_session)
    h, created = find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Софья")
    assert created
    contact = db_session.get(Contact, h.contact_id)
    assert contact.display_name == "9б класс: Софья"
    # ни группового Contact'а, ни лишних handles
    assert db_session.query(Contact).count() == 1
    assert db_session.query(MessengerHandle).count() == 1


def test_second_handle_with_same_prefix_triggers_promotion(db_session):
    user = _make_user(db_session)
    h1, _ = find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Софья")
    old_contact_id = h1.contact_id

    h2, _ = find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Вика")

    # появился групповой Contact "9б класс"
    group = db_session.query(Contact).filter(Contact.display_name == "9б класс").one()
    # оба handle теперь там
    db_session.refresh(h1)
    db_session.refresh(h2)
    assert h1.contact_id == group.id
    assert h2.contact_id == group.id
    # старый одиночный Contact удалён
    assert db_session.get(Contact, old_contact_id) is None
    # всего один Contact в БД у этого пользователя
    assert db_session.query(Contact).filter(Contact.user_id == user.id).count() == 1


def test_promotion_preserves_messages_through_handle(db_session):
    user = _make_user(db_session)
    m1 = record_message(db_session, user.id, "Telegram", "9б класс: Софья", "первое")
    record_message(db_session, user.id, "Telegram", "9б класс: Вика", "второе")

    group = db_session.query(Contact).filter(Contact.display_name == "9б класс").one()
    handle_ids = [h.id for h in db_session.query(MessengerHandle)
                  .filter(MessengerHandle.contact_id == group.id).all()]
    texts = sorted(m.text for m in db_session.query(Messages)
                   .filter(Messages.handle_id.in_(handle_ids)).all())
    assert texts == ["второе", "первое"]
    # сообщение Софьи продолжает читаться через handle_id, который теперь в группе
    db_session.refresh(m1)
    assert m1.handle_id in handle_ids


def test_third_handle_joins_existing_group(db_session):
    user = _make_user(db_session)
    find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Софья")
    find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Вика")
    contacts_before = db_session.query(Contact).count()

    h3, _ = find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Артём")

    group = db_session.query(Contact).filter(Contact.display_name == "9б класс").one()
    assert h3.contact_id == group.id
    # ничего нового не появилось
    assert db_session.query(Contact).count() == contacts_before


def test_promotion_works_cross_messenger(db_session):
    user = _make_user(db_session)
    find_or_create_handle(db_session, user.id, "Telegram", "9б класс: Софья")
    h2, _ = find_or_create_handle(db_session, user.id, "Max", "9б класс: Вика")

    group = db_session.query(Contact).filter(Contact.display_name == "9б класс").one()
    assert h2.contact_id == group.id
    assert db_session.query(MessengerHandle).filter(
        MessengerHandle.contact_id == group.id).count() == 2


def test_promotion_does_not_cross_users(db_session):
    u1 = _make_user(db_session, email="a@e.com")
    u2 = _make_user(db_session, email="b@e.com")
    find_or_create_handle(db_session, u1.id, "Telegram", "9б класс: Софья")
    find_or_create_handle(db_session, u2.id, "Telegram", "9б класс: Вика")

    groups = db_session.query(Contact).filter(Contact.display_name == "9б класс").all()
    # промоушна не было — каждый пользователь видит свой одиночный Contact
    assert len(groups) == 0
    # у каждого пользователя по одному одиночному Contact'у
    assert db_session.query(Contact).filter(Contact.user_id == u1.id).count() == 1
    assert db_session.query(Contact).filter(Contact.user_id == u2.id).count() == 1


def test_no_colon_keeps_old_behavior(db_session):
    user = _make_user(db_session)
    h1, _ = find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    h2, _ = find_or_create_handle(db_session, user.id, "Telegram", "Пётр")
    # никакого склеивания, два одиночных Contact'а
    assert h1.contact_id != h2.contact_id
    assert db_session.query(Contact).count() == 2


def test_empty_member_does_not_trigger_promotion(db_session):
    user = _make_user(db_session)
    h1, _ = find_or_create_handle(db_session, user.id, "Telegram", "X: A")
    # 'X:' — невалидный паттерн (member пустой), не считается сиблингом
    h2, _ = find_or_create_handle(db_session, user.id, "Telegram", "X:")
    # h2 идёт по обычному пути → отдельный Contact с display_name="X:"
    assert h2.contact_id != h1.contact_id
    # промоушна не было: единственный валидный handle с префиксом "X" — это h1
    assert db_session.query(Contact).filter(Contact.display_name == "X").count() == 0


def test_promotion_dismisses_pending_suggestions_for_moved_handles(db_session):
    user = _make_user(db_session)
    # сначала handle без двоеточия — потом ещё один похожий → создастся suggestion
    find_or_create_handle(db_session, user.id, "Telegram", "Иван")
    find_or_create_handle(db_session, user.id, "Telegram", "Иванn")
    assert db_session.query(MergeSuggestion).filter(
        MergeSuggestion.status == "pending").count() >= 1

    # теперь шлём групповой handle, который встречает похожий existing 'Иван'
    # (но мы хотим проверить именно cleanup при промоушне группы) — сделаем
    # пару групповых, и среди них пусть один уже имеет suggestion как target
    find_or_create_handle(db_session, user.id, "Telegram", "Группа: Кто-то")
    # пометим вручную suggestion с target_contact_id = старый одиночный группы
    src_handle = db_session.query(MessengerHandle).filter(
        MessengerHandle.sender_raw == "Иванn").first()
    grp_contact_id = db_session.query(MessengerHandle).filter(
        MessengerHandle.sender_raw == "Группа: Кто-то").first().contact_id
    db_session.add(MergeSuggestion(
        user_id=user.id, source_handle_id=src_handle.id,
        target_contact_id=grp_contact_id, score=0.9, status="pending"))
    db_session.commit()

    # промоушн группы — старый одиночный Contact "Группа: Кто-то" исчезнет
    find_or_create_handle(db_session, user.id, "Telegram", "Группа: Другой")

    # suggestion, ссылавшаяся на удалённый Contact, теперь dismissed
    sug = db_session.query(MergeSuggestion).filter(
        MergeSuggestion.target_contact_id == grp_contact_id).first()
    assert sug is not None
    assert sug.status == "dismissed"


# ---------- migrate_group_handles_v1 ----------


def test_migration_creates_group_for_existing_singletons(db_session):
    user = _make_user(db_session)
    # симулируем досюжетное состояние: 3 одиночных Contact'а
    for member in ("Софья", "Вика", "Артём"):
        c = Contact(user_id=user.id, display_name=f"9б класс: {member}")
        db_session.add(c)
        db_session.flush()
        db_session.add(MessengerHandle(
            contact_id=c.id, user_id=user.id, messenger_name="Telegram",
            sender_raw=f"9б класс: {member}", sender_normalized=f"9бкласс{member.lower()}"))
    db_session.commit()
    assert db_session.query(Contact).count() == 3

    stats = migrate_group_handles_v1(db_session)

    group = db_session.query(Contact).filter(Contact.display_name == "9б класс").one()
    assert db_session.query(MessengerHandle).filter(
        MessengerHandle.contact_id == group.id).count() == 3
    assert db_session.query(Contact).filter(Contact.user_id == user.id).count() == 1
    assert stats == {"groups_created": 1, "handles_moved": 3, "contacts_removed": 3}


def test_migration_is_idempotent(db_session):
    user = _make_user(db_session)
    for member in ("A", "B"):
        c = Contact(user_id=user.id, display_name=f"Группа: {member}")
        db_session.add(c)
        db_session.flush()
        db_session.add(MessengerHandle(
            contact_id=c.id, user_id=user.id, messenger_name="Telegram",
            sender_raw=f"Группа: {member}", sender_normalized=f"группа{member.lower()}"))
    db_session.commit()

    first = migrate_group_handles_v1(db_session)
    second = migrate_group_handles_v1(db_session)

    assert first["groups_created"] == 1
    assert second == {"groups_created": 0, "handles_moved": 0, "contacts_removed": 0}


def test_migration_ignores_singleton_prefix(db_session):
    user = _make_user(db_session)
    c = Contact(user_id=user.id, display_name="Уникум: Один")
    db_session.add(c)
    db_session.flush()
    db_session.add(MessengerHandle(
        contact_id=c.id, user_id=user.id, messenger_name="Telegram",
        sender_raw="Уникум: Один", sender_normalized="уникумодин"))
    db_session.commit()

    stats = migrate_group_handles_v1(db_session)

    assert stats == {"groups_created": 0, "handles_moved": 0, "contacts_removed": 0}
    # одиночка остаётся как есть
    assert db_session.query(Contact).filter(
        Contact.display_name == "Уникум: Один").count() == 1


def test_migration_cleans_up_orphan_contacts(db_session):
    """Сирота — Contact без единого handle (типичный артефакт ручных
    перемещений через /contacts/handles/<id>/move, который не удаляет
    опустевший Contact)."""
    user = _make_user(db_session)
    # групповой Contact с handle'ом — оставляем
    grp = Contact(user_id=user.id, display_name="9б класс")
    db_session.add(grp)
    db_session.flush()
    db_session.add(MessengerHandle(
        contact_id=grp.id, user_id=user.id, messenger_name="MAX",
        sender_raw="9б класс: Соня", sender_normalized="9бклассосоня"))
    # сирота — Contact с display_name "9б класс: Absurd", все handles давно унесли
    orphan = Contact(user_id=user.id, display_name="9б класс: Absurd")
    db_session.add(orphan)
    db_session.commit()

    stats = migrate_group_handles_v1(db_session)

    assert stats["contacts_removed"] >= 1
    assert db_session.get(Contact, orphan.id) is None
    assert db_session.get(Contact, grp.id) is not None


def test_migration_uses_existing_group_contact(db_session):
    user = _make_user(db_session)
    # групповой Contact уже есть с одним handle
    grp = Contact(user_id=user.id, display_name="Класс")
    db_session.add(grp)
    db_session.flush()
    db_session.add(MessengerHandle(
        contact_id=grp.id, user_id=user.id, messenger_name="Telegram",
        sender_raw="Класс: A", sender_normalized="классa"))
    # и есть одиночка с тем же префиксом, которую миграция должна затянуть
    lonely = Contact(user_id=user.id, display_name="Класс: B")
    db_session.add(lonely)
    db_session.flush()
    db_session.add(MessengerHandle(
        contact_id=lonely.id, user_id=user.id, messenger_name="Max",
        sender_raw="Класс: B", sender_normalized="классb"))
    db_session.commit()

    stats = migrate_group_handles_v1(db_session)

    # новый группового Contact'а не создаётся — затягиваем в существующий
    assert stats["groups_created"] == 0
    assert stats["handles_moved"] == 1
    assert stats["contacts_removed"] == 1
    assert db_session.query(Contact).filter(Contact.user_id == user.id).count() == 1
    assert db_session.query(MessengerHandle).filter(
        MessengerHandle.contact_id == grp.id).count() == 2


# ---------- маршруты ----------


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


def test_contact_detail_strips_group_prefix_in_html(client, app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="g@e.com",
             hashed_password="x")
    db.add(u); db.commit()
    record_message(db, u.id, "Telegram", "9б класс: Софья", "привет всем")
    record_message(db, u.id, "Telegram", "9б класс: Вика", "ответ")
    group = db.query(Contact).filter(Contact.display_name == "9б класс").one()
    user_id, group_id = u.id, group.id
    db.close()

    _login(client, user_id)
    resp = client.get(f"/contacts/{group_id}")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Софья" in body
    assert "Вика" in body
    # префикс группы в шапке остаётся, но рядом с сообщениями — нет
    assert "Telegram · 9б класс: Софья" not in body
    assert "Telegram · Софья" in body


def test_contact_messages_json_includes_display_author(client, app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="g2@e.com",
             hashed_password="x")
    db.add(u); db.commit()
    record_message(db, u.id, "Telegram", "9б класс: Софья", "1")
    record_message(db, u.id, "Telegram", "9б класс: Вика", "2")
    group = db.query(Contact).filter(Contact.display_name == "9б класс").one()
    user_id, group_id = u.id, group.id
    db.close()

    _login(client, user_id)
    resp = client.get(f"/contacts/{group_id}/messages.json")
    assert resp.status_code == 200
    data = resp.get_json()
    authors = sorted(m["display_author"] for m in data["messages"])
    assert authors == ["Вика", "Софья"]


def test_messages_json_keeps_sender_for_personal_contact(client, app):
    db = db_sessions.create_session()
    u = User(name="T", surname="U", sex="male", email="p@e.com",
             hashed_password="x")
    db.add(u); db.commit()
    record_message(db, u.id, "Telegram", "Иван", "привет")
    contact = db.query(Contact).filter(Contact.display_name == "Иван").one()
    user_id, contact_id = u.id, contact.id
    db.close()

    _login(client, user_id)
    resp = client.get(f"/contacts/{contact_id}/messages.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["messages"][0]["display_author"] == "Иван"
