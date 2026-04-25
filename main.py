import random
import string
from datetime import datetime

from flask import Flask, g, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from data import db_sessions
from data.users import Messages, User


_AVATAR_PALETTE = [
    "#ef4444", "#f59e0b", "#10b981", "#3b82f6",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
]


def _avatar_for(contact):
    name = (contact.display_name or "?").strip()
    contact.initial = name[:1].upper() if name else "?"
    contact.avatar_color = _AVATAR_PALETTE[contact.id % len(_AVATAR_PALETTE)]
    return contact


def _enrich_with_last_message(db, contacts):
    """Для каждого контакта подкладывает last_preview / last_time / last_at."""
    from data.contacts import MessengerHandle

    for c in contacts:
        _avatar_for(c)
        last = (
            db.query(Messages)
            .join(MessengerHandle, Messages.handle_id == MessengerHandle.id)
            .filter(MessengerHandle.contact_id == c.id)
            .order_by(Messages.created_at.desc().nullslast(), Messages.id.desc())
            .first()
        )
        if last:
            c.last_preview = last.text
            c.last_time = last.time
            c.last_at = last.created_at
        else:
            c.last_preview = None
            c.last_time = None
            c.last_at = None
    contacts.sort(
        key=lambda c: (c.last_at or datetime.min),
        reverse=True,
    )
    return contacts


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
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact, MergeSuggestion
        db = get_db()
        user = db.query(User).filter(User.id == session['user_id']).first()
        contacts_count = db.query(Contact).filter(Contact.user_id == user.id).count()
        messages_count = db.query(Messages).filter(Messages.user_id == user.id).count()
        pending_suggestions = (db.query(MergeSuggestion)
                               .filter(MergeSuggestion.user_id == user.id,
                                       MergeSuggestion.status == "pending").count())
        return render_template(
            'index.html',
            user=user,
            device_connected=bool(user.tablet_ip),
            contacts_count=contacts_count,
            messages_count=messages_count,
            pending_suggestions=pending_suggestions,
        )

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
        return redirect('/contacts')

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
            .all()
        )
        _enrich_with_last_message(db, contacts)
        return render_template('contacts.html', contacts=contacts,
                               selected=None, selected_handles=[], messages=None)

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
            .all()
        )
        _enrich_with_last_message(db, contacts)
        _avatar_for(contact)

        handles = db.query(MessengerHandle).filter(MessengerHandle.contact_id == contact.id).all()
        handle_ids = [h.id for h in handles]
        selected_handles = [f"{h.messenger_name}: {h.sender_raw}" for h in handles]
        msgs = (
            db.query(Messages)
            .filter(Messages.handle_id.in_(handle_ids))
            .order_by(Messages.created_at.desc().nullslast(), Messages.id.desc())
            .all()
        )
        return render_template('contacts.html', contacts=contacts, selected=contact,
                               selected_handles=selected_handles, messages=msgs)

    @app.route('/contacts/<int:contact_id>/messages.json')
    def contact_messages_json(contact_id):
        if not session.get('user_id'):
            return jsonify({'error': 'unauthorized'}), 401
        from data.contacts import Contact, MessengerHandle
        db = get_db()
        user_id = session['user_id']
        contact = (db.query(Contact)
                   .filter(Contact.id == contact_id, Contact.user_id == user_id).first())
        if not contact:
            return jsonify({'error': 'not_found'}), 404
        handle_ids = [h.id for h in
                      db.query(MessengerHandle).filter(MessengerHandle.contact_id == contact.id).all()]
        msgs = (db.query(Messages)
                .filter(Messages.handle_id.in_(handle_ids))
                .order_by(Messages.created_at.desc().nullslast(), Messages.id.desc())
                .all())
        return jsonify({'messages': [
            {'id': m.id, 'sender': m.sender, 'text': m.text,
             'messenger_name': m.messenger_name, 'time': m.time}
            for m in msgs
        ]})

    @app.route('/contacts/manage')
    def contacts_manage():
        if not session.get('user_id'):
            return redirect('/login')
        from data.contacts import Contact, MergeSuggestion, MessengerHandle
        db = get_db()
        user_id = session['user_id']
        all_contacts = (db.query(Contact).filter(Contact.user_id == user_id)
                        .order_by(Contact.display_name.asc()).all())
        for c in all_contacts:
            _avatar_for(c)
        handles = (db.query(MessengerHandle).filter(MessengerHandle.user_id == user_id)
                   .order_by(MessengerHandle.messenger_name.asc()).all())
        contact_handles = {c.id: [] for c in all_contacts}
        for h in handles:
            contact_handles.setdefault(h.contact_id, []).append(h)
        suggestions = (db.query(MergeSuggestion)
                       .filter(MergeSuggestion.user_id == user_id,
                               MergeSuggestion.status == "pending")
                       .order_by(MergeSuggestion.score.desc()).all())
        return render_template('contacts_manage.html',
                               all_contacts=all_contacts,
                               contact_handles=contact_handles,
                               suggestions=suggestions)

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
        source_handle = db.get(MessengerHandle, sug.source_handle_id)
        try:
            merge_contacts(db, user_id, source_handle.contact_id, sug.target_contact_id)
        except (ValueError, LookupError):
            return 'Conflict', 409
        sug.status = "accepted"
        db.commit()
        return redirect('/contacts/manage')

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


def _generate_code() -> str:
    return ''.join(random.choices(string.digits, k=8))


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=True)
