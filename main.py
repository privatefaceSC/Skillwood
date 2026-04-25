from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import sqlalchemy
from data.users import User
from data import db_sessions
from flask import Flask, request, render_template_string
import sqlite3
from datetime import datetime
from forms.user import RegisterForm
from data import db_sessions
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
import random
import string
from data.users import Messages


db_sessions.global_init("db/blogs.db")
db_sess = db_sessions.create_session()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'


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
    user = db_sess.query(User).filter(User.id == session['user_id']).first()
    return render_template('index.html', user=user)

def generate_code():
    return ''.join(random.choices(string.digits, k=8))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        surname = request.form.get('surname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        sex = request.form.get('sex')

        if password != confirm_password:
            return render_template('register.html', message="Пароли не совпадают")

        if db_sess.query(User).filter(User.email == email).first():
            return render_template('register.html', message="Такой пользователь уже есть")

        user = User(
            name=name,
            surname=surname,
            email=email,
            sex=sex,
            hashed_password=generate_password_hash(password)
        )
        user.connect_code = generate_code()

        db_sess.add(user)
        db_sess.commit()
        session['user_id'] = user.id

        return redirect('/code')
    return render_template('register.html')

@app.route('/code')
def code():
    if not session.get('user_id'):
        return redirect('/login')

    user = db_sess.query(User).filter(User.id == session['user_id']).first()
    if user.tablet_ip:
        return redirect('/home')

    return render_template('code.html', code=user.connect_code)


@app.route('/connect', methods=['GET'])
def connect_tablet():
    code = request.args.get('code')
    tablet_ip = request.remote_addr
    print(f"Получен код {code} от пользователя с айпи: {tablet_ip}")

    user = db_sess.query(User).filter(User.connect_code == code).first()

    if user:
        user.tablet_ip = tablet_ip
        db_sess.commit()
        print(f"Устройство подключёно к пользователю {user.name}")
        return "OK", 200
    else:
        print("Неверный код")
        return "Неверный код", 404

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db_sess.query(User).filter(User.email == email).first()
        if user and check_password_hash(user.hashed_password, password):
            session['user_id'] = user.id
            return redirect('/home')
        else:
            return render_template('login.html', message="Неверный email или пароль")

    return render_template('login.html')


@app.route('/messages')
def messages():
    if not session.get('user_id'):
        return redirect('/login')

    user_id = session['user_id']
    messages = db_sess.query(Messages).filter(Messages.user_id == user_id).order_by(Messages.id.desc()).all()
    return render_template('chats.html', messages=messages)


@app.route('/add', methods=['POST'])
def add_message():
    sender = request.form.get('sender')
    text = request.form.get('text')
    messenger_name = request.form.get('messenger_name')
    tablet_ip = request.remote_addr

    user = db_sess.query(User).filter(User.tablet_ip == tablet_ip).first()
    if not user:
        print(f"Неизвестное устройство с IP: {tablet_ip}")
        return 'OK', 200

    time_now = datetime.now().strftime('%H:%M')

    new_message = Messages(
        sender=sender,
        text=text,
        messenger_name=messenger_name,
        time=time_now,
        user_id=user.id
    )
    db_sess.add(new_message)
    db_sess.commit()

    print(f"из {messenger_name}, Пользователю {user.name}: От {sender} - {text}")
    return 'OK', 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)