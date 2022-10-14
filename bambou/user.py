from functools import partial, wraps

from flask import abort, g, session

from .db import get_connection


def get():
    if 'person_id' not in session:
        return None
    if not hasattr(g, 'person'):
        cursor = get_connection().cursor()
        cursor.execute(
            'SELECT * FROM person WHERE id = (?)',
            (session['person_id'],))
        g.person = cursor.fetchone()
    return g.person


def check(*roles):
    def wrap(function):
        @wraps(function)
        def check_auth(*args, **kwargs):
            for role in roles:
                if role():
                    return function(*args, **kwargs)
            return abort(403)
        return check_auth
    return wrap


def _is_role(table_name):
    user = get()
    if user is None:
        return False
    cursor = get_connection().cursor()
    cursor.execute(
        f'SELECT * FROM {table_name} WHERE person_id = (?)',
        (user['id'],))
    return cursor.fetchone()


is_tutor = partial(_is_role, table_name='tutor')
is_teacher = partial(_is_role, table_name='teacher')
is_student = partial(_is_role, table_name='student')
is_administrator = partial(_is_role, table_name='administrator')
is_superadministrator = partial(_is_role, table_name='superadministrator')
is_connected = get
