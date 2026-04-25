import flask
from flask import jsonify, make_response, request

from . import db_sessions
from .users import User

blueprint = flask.Blueprint(
    'user_api',
    __name__,
    template_folder='templates'
)


@blueprint.route('/api/user')
def get_user():
    db_sess = db_sessions.create_session()
    user = db_sess.query(User).all()
    return jsonify(
        {
            'user':
                [item.to_dict(only=('name', 'surname', 'about', 'email'))
                 for item in user]
        }
    )

@blueprint.route('/api/user/<int:user_id>', methods=['GET'])
def get_one_user(user_id):
    db_sess = db_sessions.create_session()
    user = db_sess.get(User, user_id)
    if not user:
        return make_response(jsonify({'error': 'Not found'}), 404)
    return jsonify(
        {
            'user': user.to_dict(only=(
                'name', 'surname', 'about', 'email'))
        }
    )
@blueprint.route('/api/user', methods=['POST'])
def create_user():
    if not request.json:
        return make_response(jsonify({'error': 'Empty request'}), 400)
    elif not all(key in request.json for key in
                 ['name', 'surname', 'about', 'email']):
        return make_response(jsonify({'error': 'Bad request'}), 400)
    db_sess = db_sessions.create_session()
    user = User(
        name=request.json['name'],
        surname=request.json['surname'],
        about=request.json['about'],
        email=request.json['email']
    )
    db_sess.add(user)
    db_sess.commit()
    return jsonify({'id': user.id})

@blueprint.route('/api/editing_user/<int:user_id>', methods=['PUT'])
def editing_user(user_id):
    db_sess = db_sessions.create_session()
    user = db_sess.get(User, user_id)

    if not user:
        return make_response(jsonify({'error': 'Not found'}), 404)

    user.name = request.json['name']
    user.surname = request.json['surname']
    user.about = request.json['about']
    user.email = request.json['email']
    db_sess.commit()
    return jsonify({'id': user.id, 'new_name': user.name})



@blueprint.route('/api/user/delete/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    db_sess = db_sessions.create_session()
    user = db_sess.get(User, user_id)
    if not user:
        return make_response(jsonify({'error': 'Not found'}), 404)
    db_sess.delete(user)
    db_sess.commit()
    return jsonify({'success': 'OK'})


