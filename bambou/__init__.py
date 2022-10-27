from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

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
            'SELECT id, password FROM person WHERE mail = ?',
            (request.form['login'],))
        person = cursor.fetchone()
        if person:
            passwords = request.form['password'], person['password']
            if check_password_hash(*passwords) or app.config['DEBUG']:
                session['person_id'] = person['id']
                return redirect(url_for('index'))
        flash('L’identifiant ou le mot de passe est incorrect')
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    session.pop('person_id', None)
    return redirect(url_for('login'))


@app.route('/tutor')
def tutor():
    # TODO
    pass


@app.route('/profile', methods=('GET', 'POST'))
@app.route('/profile/<int:person_id>', methods=('GET', 'POST'))
@user.check(user.is_connected)
def profile(person_id=None):
    if person_id == session['person_id']:
        return redirect(url_for('profile'))
    elif person_id is None:
        person_id = session['person_id']
    elif not user.is_superadministrator():
        return abort(403)

    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        if request.form['password'] != request.form['confirm_password']:
            flash('Les deux mots de passe doivent être les mêmes')
            return redirect(url_for('profile', person_id=person_id))
        if user.is_superadministrator():
            parameters = (
                request.form['mail'], request.form['firstname'],
                request.form['lastname'], person_id)
            cursor.execute('''
                UPDATE person
                SET mail = ?, firstname = ?, lastname = ?
                WHERE rowid = ?
            ''', parameters)
        else:
            cursor.execute(
                'UPDATE person SET mail = ? WHERE rowid = ?',
                (request.form['mail'], person_id))
        if request.form['password']:
            cursor.execute(
                'UPDATE person SET password = ? WHERE rowid = ?',
                (generate_password_hash(request.form['password']), person_id))
        connection.commit()
        flash('Les informations ont été sauvegardées')
        return redirect(url_for('profile', person_id=person_id))
    cursor.execute('SELECT * FROM person WHERE rowid = ?', (person_id,))
    person = cursor.fetchone()
    return render_template('profile.jinja2.html', person=person)


@app.route('/profile/add>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def profile_add():
    return render_template('profile_add.jinja2.html')


@app.route('/teacher')
@user.check(user.is_teacher)
def teacher():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          teaching_period.id AS teaching_period_id,
          teaching_period.name AS teaching_period_name,
          production_action.id AS production_action_id,
          production_action.name AS production_action_name
        FROM
          teacher
        JOIN
          production_action ON (production_action.teacher_id = teacher.id),
          course ON (course.production_action_id = production_action.id),
          semester ON (semester.id = course.semester_id),
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        WHERE
          teacher.person_id = ?
    ''', (session['person_id'],))
    courses = cursor.fetchall()
    return render_template('teacher.jinja2.html', courses=courses)


@app.route('/marks/<int:production_action_id>', methods=('GET', 'POST'))
@user.check(user.is_teacher, user.is_superadministrator)
def marks(production_action_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT
          production_action.name AS production_action_name,
          group_concat(teaching_period.name, ', ') AS teaching_period_names
        FROM
          course
        JOIN
          semester ON (semester.id = course.semester_id),
          teaching_period ON (
            teaching_period.id = semester.teaching_period_id),
          production_action ON (
            production_action.id = course.production_action_id)
        WHERE
          course.production_action_id = ?
        GROUP BY
          teaching_period.name
        ORDER BY
          teaching_period.name
    ''', (production_action_id,))
    course = cursor.fetchone()
    cursor.execute('''
        SELECT
          person.lastname || ' ' || person.firstname AS person_name,
          assignment.id,
          assignment.mark,
          assignment.comments
        FROM
          course
        JOIN
          assignment ON (assignment.course_id = course.id),
          registration ON (registration.id = assignment.registration_id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        WHERE
          course.production_action_id = ?
        ORDER BY
          person.lastname
    ''', (production_action_id,))
    assignments = cursor.fetchall()
    if request.method == 'POST':
        for assignment in assignments:
            values = (
                request.form[f'{assignment["id"]}-mark'] or None,
                request.form[f'{assignment["id"]}-comments'] or None,
                assignment['id'])
            cursor.execute('''
                UPDATE
                  assignment
                SET
                  mark = ?,
                  comments = ?
                WHERE
                  assignment.id = ?
            ''', values)
        connection.commit()
        flash('Les notes ont été enregistrées')
        return redirect(url_for(
            'marks', production_action_id=production_action_id))
    return render_template(
        'marks.jinja2.html', assignments=assignments, course=course)


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
              student.person_id = ?
        ''', (session['person_id'],))
        registration = cursor.fetchone()
        if registration:
            registration_id = registration['id']
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
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        JOIN
          registration ON (
            registration.teaching_period_id = teaching_period.id)
        JOIN
          assignment ON (assignment.registration_id = registration.id)
        LEFT JOIN
          tracking ON (tracking.semester_id = semester.id)
        JOIN
          course ON (
            course.id = assignment.course_id AND
            course.semester_id = semester.id)
        JOIN
          production_action ON (
            production_action.id = course.production_action_id)
        WHERE
          registration.id = ?
        ORDER BY
          semester.start,
          production_action.last_course_date,
          production_action.name
    ''', (registration_id,))
    marks = cursor.fetchall()
    cursor.execute('''
        SELECT
          person.firstname || ' ' || person.lastname AS name,
          teaching_period.name AS teaching_period_name
        FROM
          person
        JOIN
          student ON (person.id = student.person_id),
          registration ON (registration.student_id = student.id),
          teaching_period ON (
            teaching_period.id = registration.teaching_period_id)
        WHERE
          registration.id = ?
    ''', (registration_id,))
    person = cursor.fetchone()
    return render_template('report.jinja2.html', marks=marks, person=person)


@app.route('/administrator')
@user.check(user.is_administrator)
def administrator():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          person.firstname || ' ' || person.lastname AS person_name,
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
        ORDER BY
          teaching_period.name
    ''')
    teaching_periods = cursor.fetchall()
    cursor.execute('''
        SELECT
          production_action.id,
          production_action.name,
          group_concat(teaching_period.name, ', ') as teaching_period_names
        FROM
          production_action
        LEFT JOIN
          course ON (course.production_action_id = production_action.id)
        LEFT JOIN
          semester ON (semester.id = course.semester_id)
        LEFT JOIN
          teaching_period on (teaching_period.id = semester.teaching_period_id)
        GROUP BY
          production_action.id, teaching_period.name
        ORDER BY
          production_action.name
    ''')
    production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT
          person.id,
          person.lastname || ' ' || person.firstname as person_name
        FROM
          person
        ORDER BY
          person.lastname
    ''')
    people = cursor.fetchall()
    return render_template(
        'superadministrator.jinja2.html', teaching_periods=teaching_periods,
        production_actions=production_actions, people=people)


@app.route('/teaching-period/<int:teaching_period_id>',
           methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def teaching_period(teaching_period_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            UPDATE
              teaching_period
            SET
              code = ?,
              name = ?
            WHERE
              teaching_period.id = ?
        ''', (request.form['code'], request.form['name'], teaching_period_id))
        connection.commit()
        flash('La période de formation a été modifiée')
        return redirect(url_for(
            'teaching_period', teaching_period_id=teaching_period_id))
    cursor.execute('''
        SELECT
          teaching_period.code,
          teaching_period.name
        FROM
          teaching_period
        WHERE
          teaching_period.id = ?
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
          semester.teaching_period_id = ?
        ORDER BY
          production_action.name
    ''', (teaching_period_id,))
    production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT
          person.id,
          person.lastname || ' ' || person.firstname as person_name
        FROM
          person
        JOIN
          student ON (student.person_id = person.id),
          registration ON (registration.student_id = student.id)
        WHERE
          registration.teaching_period_id = ?
        ORDER BY
          person.lastname
    ''', (teaching_period_id,))
    students = cursor.fetchall()
    return render_template(
        'teaching_period.jinja2.html', teaching_period=teaching_period,
        production_actions=production_actions, students=students)


@app.route('/teaching-period/add>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def teaching_period_add():
    return render_template('teaching_period_add.jinja2.html')


@app.route('/production-action/<int:production_action_id>',
           methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def production_action(production_action_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        values = (
            request.form['code'],
            request.form['name'],
            request.form['teacher_id'],
            request.form['last_course_date'],
            production_action_id)
        cursor.execute('''
            UPDATE
              production_action
            SET
              code = ?,
              name = ?,
              teacher_id = ?,
              last_course_date = ?
            WHERE
              production_action.id = ?
        ''', values)
        connection.commit()
        flash('L’action de production a été modifiée')
        return redirect(url_for(
            'production_action', production_action_id=production_action_id))
    cursor.execute('''
        SELECT
          production_action.code,
          production_action.name,
          production_action.teacher_id,
          production_action.last_course_date
        FROM
          production_action
        WHERE
          production_action.id = ?
    ''', (production_action_id,))
    production_action = cursor.fetchone()
    cursor.execute('''
        SELECT
          teacher.id,
          person.lastname || ' ' || person.firstname AS name
        FROM
          teacher
        JOIN
          person ON (person.id = teacher.person_id)
        ORDER BY
          person.lastname
    ''')
    teachers = cursor.fetchall()
    return render_template(
        'production_action.jinja2.html', production_action=production_action,
        teachers=teachers)


@app.route('/production_action/add>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def production_action_add():
    return render_template('production_action_add.jinja2.html')


@app.route('/semester/add>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def semester():
    return render_template('semester.jinja2.html')


@app.route('/mark', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def mark():
    return render_template('mark.jinja2.html')


@app.route('/mark_special', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def mark_special():
    return render_template('mark_special.jinja2.html')


@app.route('/semester_comment', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def semester_comment():
    return render_template('semester_comment.jinja2.html')


@app.route('/absences', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def absences():
    return render_template('absences.jinja2.html')


@app.route('/lost_password', methods=('GET', 'POST'))
def lost_password():
    return render_template('lost_password.jinja2.html')


@app.route('/reset_password', methods=('GET', 'POST'))
def reset_password():
    return render_template('reset_password.jinja2.html')


@app.template_filter()
def hours(minutes):
    minutes = minutes or 0
    return (
        f'{minutes} min' if minutes < 60 else
        f'{minutes//60} h {minutes%60:02}')


@app.context_processor
def inject_variables():
    return {'user': user}
