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
    app.run(host='0.0.0.0', port=5000, debug=False)
