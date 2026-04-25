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
