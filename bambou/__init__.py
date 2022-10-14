from flask import (
    Flask, abort, redirect, render_template, request, session, url_for)

from . import user
from .db import get_connection

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='bambou.db')
app.config.from_envvar('BAMBOU_CONFIG', silent=True)


@app.route('/')
def index():
    if user.is_tutor():
        pass
    elif user.is_teacher():
        return redirect(url_for('teacher'))
    elif user.is_student():
        return redirect(url_for('report'))
    elif user.is_administrator():
        return redirect(url_for('administrator'))
    elif user.is_superadministrator():
        return redirect(url_for('superadministrator'))
    return redirect(url_for('login'))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        cursor.execute(
            'SELECT id FROM person WHERE mail = (?)',
            (request.form['login'],))
        person = cursor.fetchone()
        if person:
            session['person_id'] = person['id']
            return redirect(url_for('index'))
        else:
            pass
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    session.pop('person_id', None)
    return redirect(url_for('login'))


@app.route('/profile', methods=('GET', 'POST'))
@app.route('/profile/<int:person_id>', methods=('GET', 'POST'))
@user.check(user.is_connected)
def profile(person_id=None):
    if person_id is None:
        person_id = session['person_id']
    else:
        if not user.is_superadministrator():
            return abort(403)

    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            UPDATE person
            SET
              mail = (?),
              firstname = (?),
              lastname = (?),
              password = (?)
            WHERE
              rowid = (?)
        ''', (
            request.form['mail'], request.form['firstname'],
            request.form['lastname'], request.form['password'], person_id))
        connection.commit()
        return redirect(url_for('profile', person_id=person_id))
    cursor.execute('SELECT * FROM person WHERE rowid = (?)', (person_id,))
    person = cursor.fetchone()
    return render_template('profile.jinja2.html', person=person)


@app.route('/teacher')
@user.check(user.is_teacher)
def teacher():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          teaching_period.id AS teaching_period_id,
          teaching_period.name AS teaching_period_name,
          production_action.name AS production_action_name
        FROM
          teacher
        JOIN
          production_action ON (production_action.teacher_id = teacher.id),
          course ON (course.production_action_id = production_action.id),
          semester ON (semester.id = course.semester_id),
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        WHERE
          teacher.person_id = (?)
    ''', (session['person_id'],))
    courses = cursor.fetchall()
    return render_template('teacher.jinja2.html', courses=courses)


@app.route('/marks/<int:course_id>', methods=('GET', 'POST'))
@user.check(user.is_teacher, user.is_superadministrator)
def marks(course_id):
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          person.firstname || ' ' || person.lastname as person_name,
          assignment.mark,
          assignment.comments
        FROM
          assignment
        JOIN
          registration ON (registration.id = assignment.registration_id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        WHERE
          assignment.course_id = (?)
    ''', (course_id,))
    assignments = cursor.fetchall()
    return render_template('marks.jinja2.html', assignments=assignments)


@app.route('/report')
@app.route('/report/<int:registration_id>')
@user.check(user.is_student, user.is_administrator, user.is_superadministrator)
def report(registration_id=None):
    cursor = get_connection().cursor()
    if registration_id is None:
        cursor.execute('''
            SELECT
              registration.id
            FROM
              registration
            JOIN
              student ON (student.id = registration.student_id)
            WHERE
              student.person_id = (?)
        ''', (session['person_id'],))
        registration = cursor.fetchone()
        if registration:
            registration_id = session['person_id']
        else:
            return abort(404)
    else:
        if not (user.is_administrator() or user.is_superadministrator()):
            return abort(403)

    cursor.execute('''
        SELECT
          production_action.name AS production_action_name,
          semester.id AS semester_id,
          semester.name AS semester_name,
          tracking.justified_absence_minutes,
          tracking.unjustified_absence_minutes,
          tracking.lateness_minutes,
          tracking.comments AS tracking_comments,
          assignment.course_id,
          assignment.mark,
          assignment.comments
        FROM
          semester
        JOIN
          tracking ON (tracking.semester_id = semester.id)
        LEFT JOIN
          assignment AS registration_assignment ON (
            registration_assignment.registration_id = tracking.registration_id)
        LEFT JOIN
          course ON (
            course.id = registration_assignment.course_id AND
            course.semester_id = semester.id)
        LEFT JOIN
          assignment ON (assignment.course_id = course.id)
        LEFT JOIN
          production_action ON (
            production_action.id = course.production_action_id)
        WHERE
          registration_assignment.registration_id = (?)
    ''', (registration_id,))
    marks = cursor.fetchall()
    return render_template('report.jinja2.html', marks=marks)


@app.route('/administrator')
@user.check(user.is_administrator)
def administrator():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          person.firstname || ' ' || person.lastname as person_name,
          teaching_period.id AS teaching_period_id,
          teaching_period.name AS teaching_period_name
        FROM
          teaching_period
        JOIN
          registration ON (
            registration.teaching_period_id = teaching_period.id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
    ''')
    students = cursor.fetchall()
    return render_template('administrator.jinja2.html', students=students)


@app.route('/superadministrator', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def superadministrator():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          teaching_period.id,
          teaching_period.name
        FROM
          teaching_period
    ''')
    training_periods = cursor.fetchall()
    cursor.execute('''
        SELECT
          production_action.id,
          production_action.name
        FROM
          production_action
    ''')
    production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT
          person.id,
          person.firstname || ' ' || person.lastname as person_name
        FROM
          person
    ''')
    people = cursor.fetchall()
    return render_template(
        'superadministrator.jinja2.html', training_periods=training_periods,
        production_actions=production_actions, people=people)


@app.route('/teaching-period/<int:teaching_period_id>',
           methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def teaching_period(teaching_period_id):
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          teaching_period.code,
          teaching_period.name
        FROM
          teaching_period
        WHERE
          teaching_period.id = (?)
    ''', (teaching_period_id,))
    teaching_period = cursor.fetchone()
    cursor.execute('''
        SELECT
          production_action.id,
          production_action.name
        FROM
          production_action
        JOIN
          course ON (course.production_action_id = production_action.id),
          semester ON (semester.id = course.semester_id)
        WHERE
          semester.teaching_period_id = (?)
    ''', (teaching_period_id,))
    production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT
          person.id,
          person.firstname || ' ' || person.lastname as person_name
        FROM
          person
        JOIN
          student ON (student.person_id = person.id),
          registration ON (registration.student_id = student.id)
        WHERE
          registration.teaching_period_id = (?)
    ''', (teaching_period_id,))
    students = cursor.fetchall()
    return render_template(
        'teaching_period.jinja2.html', teaching_period=teaching_period,
        production_actions=production_actions, students=students)
