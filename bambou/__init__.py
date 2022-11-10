from email.message import EmailMessage
from smtplib import SMTP_SSL
from uuid import uuid4

from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import user
from .db import close_connection, get_connection

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='bambou.db')
app.config.from_envvar('BAMBOU_CONFIG', silent=True)


@app.route('/')
def index():
    if user.is_superadministrator():
        return redirect(url_for('superadministrator'))
    elif user.is_administrator():
        return redirect(url_for('administrator'))
    elif user.is_teacher():
        return redirect(url_for('teacher'))
    elif user.is_tutor():
        return redirect(url_for('tutor'))
    elif user.is_student():
        return redirect(url_for('report'))
    return redirect(url_for('login'))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        cursor.execute(
            'SELECT id, password FROM person WHERE mail = ?',
            (request.form['login'],))
        person = cursor.fetchone()
        if person and (app.config['DEBUG'] or person['password']):
            passwords = person['password'], request.form['password']
            if app.config['DEBUG'] or check_password_hash(*passwords):
                session['person_id'] = person['id']
                return redirect(url_for('index'))
        flash('L’identifiant ou le mot de passe est incorrect')
        return redirect(url_for('login'))
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    session.pop('person_id', None)
    return redirect(url_for('login'))


@app.route('/tutor')
@user.check(user.is_tutor)
def tutor():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          person.lastname || ' ' || person.firstname AS person_name,
          registration.id AS registration_id
        FROM
          tutor
        JOIN
          tutoring ON (tutoring.tutor_id = tutor.id),
          registration ON (registration.id = tutoring.registration_id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        WHERE
          tutor.person_id = ?
    ''', (session['person_id'],))
    students = cursor.fetchall()
    if len(students) == 1:
        return redirect(url_for(
            'report', registration_id=students[0]['registration_id']))
    return render_template('tutor.jinja2.html', students=students)


@app.route('/tutoring/add/<int:tutor_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def tutoring_add(tutor_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        INSERT INTO tutoring (tutor_id, registration_id)
        VALUES (?, ?)
    ''', (tutor_id, request.form['registration_id']))
    connection.commit()
    flash('L’apprenant a été assigné au tuteur')
    return redirect(request.referrer)


@app.route('/tutoring/tutoring/<int:tutoring_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def tutoring_delete(tutoring_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('DELETE FROM tutoring WHERE id = ?', (tutoring_id,))
    connection.commit()
    flash('L’apprenant a été retiré au tuteur')
    return redirect(request.referrer)


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
    cursor.execute('''
        SELECT
          student.id AS student,
          tutor.id AS tutor,
          teacher.id AS teacher,
          administrator.id AS administrator,
          superadministrator.id AS superadministrator
        FROM
          person
        LEFT JOIN
          student ON (student.person_id = ?)
        LEFT JOIN
          tutor ON (tutor.person_id = ?)
        LEFT JOIN
          teacher ON (teacher.person_id = ?)
        LEFT JOIN
          administrator ON (administrator.person_id = ?)
        LEFT JOIN
          superadministrator ON (superadministrator.person_id = ?)
    ''', (person_id,) * 5)
    roles = cursor.fetchone()

    if request.method == 'POST':
        password_match = (
            request.form.get('password') ==
            request.form.get('confirm_password'))
        if not password_match:
            flash('Les deux mots de passe doivent être les mêmes')
            return redirect(url_for('profile', person_id=person_id))
        if user.is_superadministrator():
            parameters = (
                request.form['mail'], request.form['firstname'],
                request.form['lastname'], person_id)
            cursor.execute('''
                UPDATE person
                SET mail = ?, firstname = ?, lastname = ?
                WHERE id = ?
            ''', parameters)
            current_roles = {role for role in user.ROLES if roles[role]}
            new_roles = {role for role in user.ROLES if role in request.form}
            print(current_roles, new_roles, dict(roles), request.form)
            for removed_role in current_roles - new_roles:
                cursor.execute(
                    f'DELETE FROM {removed_role} WHERE person_id = ?',
                    (person_id,))
            for added_role in new_roles - current_roles:
                cursor.execute(
                    f'INSERT INTO {added_role} (person_id) VALUES (?)',
                    (person_id,))
        else:
            cursor.execute(
                'UPDATE person SET mail = ? WHERE id = ?',
                (request.form['mail'], person_id))
        if request.form.get('password'):
            cursor.execute(
                'UPDATE person SET password = ? WHERE id = ?',
                (generate_password_hash(request.form['password']), person_id))
        connection.commit()
        flash('Les informations ont été sauvegardées')
        return redirect(url_for('profile', person_id=person_id))
    cursor.execute('SELECT * FROM person WHERE id = ?', (person_id,))
    person = cursor.fetchone()
    extra_data = {}
    if roles['student']:
        cursor.execute('''
            SELECT
              registration.id,
              teaching_period.id AS teaching_period_id,
              teaching_period.name AS teaching_period_name
            FROM
              registration
            JOIN
              teaching_period ON (
                teaching_period.id = registration.teaching_period_id)
            WHERE
              student_id = ?
        ''', (roles['student'],))
        extra_data['registrations'] = cursor.fetchall()
        cursor.execute('SELECT id, name FROM teaching_period ORDER BY name')
        extra_data['teaching_periods'] = cursor.fetchall()
    if roles['tutor']:
        cursor.execute('''
            SELECT
              tutoring.id,
              registration.id AS registration_id,
              person.lastname || ' ' || person.firstname AS person_name,
              person.mail AS person_mail
            FROM
              tutoring
            JOIN
              registration ON (registration.id = tutoring.registration_id),
              student ON (student.id = registration.student_id),
              person ON (person.id = student.person_id)
            WHERE
              tutoring.tutor_id = ?
            ORDER BY
              person_name
        ''', (roles['tutor'],))
        extra_data['tutorings'] = cursor.fetchall()
        cursor.execute('''
            SELECT
              registration.id,
              person.lastname || ' ' || person.firstname as person_name,
              teaching_period.name AS teaching_period_name
            FROM
              registration
            JOIN
              student ON (student.id = registration.student_id),
              person ON (person.id = student.person_id),
              teaching_period ON (
                teaching_period.id = registration.teaching_period_id)
            ORDER BY
              person_name
        ''')
        extra_data['registrations'] = cursor.fetchall()
    if roles['teacher']:
        extra_data['production_actions'] = cursor.fetchall()
        cursor.execute('''
            SELECT
              production_action.id,
              production_action.name,
              production_action.teacher_id,
              group_concat(teaching_period.name, ', ') AS teaching_period_names
            FROM
              production_action
            LEFT JOIN
              course ON (course.production_action_id = production_action.id)
            LEFT JOIN
              semester ON (semester.id = course.semester_id)
            LEFT JOIN
              teaching_period ON (
                teaching_period.id = semester.teaching_period_id)
            GROUP BY
              production_action.id
            ORDER BY
              production_action.name
        ''')
        extra_data['production_actions'] = cursor.fetchall()
    return render_template(
        'profile.jinja2.html', person=person, roles=roles, **extra_data)


@app.route('/profile/add', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def profile_add():
    if request.method == 'POST':
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute('''
            INSERT INTO person (mail, firstname, lastname)
            VALUES (:mail, :firstname, :lastname)
            RETURNING id
        ''', request.form)
        person_id = cursor.fetchone()['id']
        for role in user.ROLES:
            if role in request.form:
                cursor.execute(f'''
                    INSERT INTO {role} (person_id)
                    VALUES (:mail)
                ''', (person_id,))
        connection.commit()
        flash('Le compte de la personne a été créé')
        return redirect(url_for('index'))
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
          production_action.name
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
@user.check(
    user.is_student, user.is_tutor, user.is_administrator,
    user.is_superadministrator)
def report(registration_id=None):
    cursor = get_connection().cursor()
    if registration_id is None:
        cursor.execute('''
            SELECT registration.id
            FROM registration
            JOIN student ON (student.id = registration.student_id)
            WHERE student.person_id = ?
        ''', (session['person_id'],))
        registration = cursor.fetchone()
        if registration:
            registration_id = registration['id']
        else:
            return abort(404)
    else:
        if user.is_tutor():
            cursor.execute('''
                SELECT registration.id
                FROM registration
                JOIN tutoring ON (tutoring.registration_id = registration.id)
                JOIN tutor ON (tutor.id = tutoring.tutor_id)
                WHERE tutor.person_id = ? AND registration.id = ?
            ''', (session['person_id'], registration_id))
            if not cursor.fetchone():
                return abort(403)
        elif not (user.is_administrator() or user.is_superadministrator()):
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
          course.id AS course_id,
          assignment.id,
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
    assignments = cursor.fetchall()
    cursor.execute('''
        SELECT
          examination.id,
          examination.name,
          examination_mark.mark,
          examination_mark.comments
        FROM
          examination
        JOIN
          teaching_period ON (
            teaching_period.id = examination.teaching_period_id),
          registration ON (
            registration.teaching_period_id = teaching_period.id)
        LEFT JOIN
          examination_mark ON (
            examination_mark.examination_id = examination.id AND
            examination_mark.registration_id = ?)
        WHERE
          registration.id = ?
        ORDER BY
          examination.name
    ''', (registration_id, registration_id))
    examinations = cursor.fetchall()
    cursor.execute('''
        SELECT
          student.id,
          person.firstname || ' ' || person.lastname AS name,
          teaching_period.name AS teaching_period_name,
          registration.id AS registration_id
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
    student = cursor.fetchone()
    cursor.execute('''
        SELECT
          course.id,
          production_action.name
        FROM
          registration
        JOIN
          teaching_period ON (
            teaching_period.id = registration.teaching_period_id),
          semester ON (semester.teaching_period_id = teaching_period.id),
          course ON (course.semester_id = semester.id),
          production_action ON (
            production_action.id = course.production_action_id)
        WHERE
          registration.id = ?
    ''', (registration_id,))
    courses = cursor.fetchall()
    return render_template(
        'report.jinja2.html', assignments=assignments, student=student,
        examinations=examinations, courses=courses)


@app.route('/administrator')
@user.check(user.is_administrator)
def administrator():
    query_search = request.args.to_dict().get('search')
    sql_search = f'%{query_search or ""}%'
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          person.lastname || ' ' || person.firstname AS person_name,
          teaching_period.id AS teaching_period_id,
          teaching_period.name AS teaching_period_name,
          registration.id AS registration_id
        FROM
          teaching_period
        JOIN
          registration ON (
            registration.teaching_period_id = teaching_period.id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        WHERE
          person.firstname LIKE ? OR
          person.lastname LIKE ?
        ORDER BY
          person.lastname
    ''', (sql_search, sql_search))
    students = cursor.fetchall()
    return render_template('administrator.jinja2.html', students=students)


@app.route('/superadministrator')
@user.check(user.is_superadministrator)
def superadministrator():
    query_search = request.args.to_dict().get('search')
    sql_search = f'%{query_search or ""}%'
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT id, name
        FROM teaching_period
        WHERE name LIKE ?
        ORDER BY teaching_period.name
    ''', (sql_search,))
    teaching_periods = cursor.fetchall()
    cursor.execute('''
        SELECT
          production_action.id,
          production_action.name,
          group_concat(teaching_period.name, ', ') AS teaching_period_names
        FROM
          production_action
        LEFT JOIN
          course ON (course.production_action_id = production_action.id)
        LEFT JOIN
          semester ON (semester.id = course.semester_id)
        LEFT JOIN
          teaching_period on (teaching_period.id = semester.teaching_period_id)
        WHERE
          production_action.name LIKE ?
        GROUP BY
          production_action.id, teaching_period.name
        ORDER BY
          production_action.name
    ''', (sql_search,))
    production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT id, person.lastname || ' ' || person.firstname as person_name
        FROM person
        WHERE firstname LIKE ? OR lastname LIKE ?
        ORDER BY person.lastname
    ''', (sql_search, sql_search))
    people = cursor.fetchall()
    return render_template(
        'superadministrator.jinja2.html', teaching_periods=teaching_periods,
        production_actions=production_actions, people=people,
        search=query_search)


@app.route('/teaching-period/<int:teaching_period_id>',
           methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def teaching_period(teaching_period_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            UPDATE teaching_period
            SET code = ?, name = ?
            WHERE teaching_period.id = ?
        ''', (request.form['code'], request.form['name'], teaching_period_id))
        connection.commit()
        flash('La période de formation a été modifiée')
        return redirect(url_for(
            'teaching_period', teaching_period_id=teaching_period_id))
    cursor.execute('''
        SELECT id, code, name
        FROM teaching_period
        WHERE id = ?
    ''', (teaching_period_id,))
    teaching_period = cursor.fetchone()
    cursor.execute('''
        SELECT
          production_action.id,
          production_action.name,
          course.id AS course_id,
          semester.id AS semester_id,
          semester.start AS semester_start,
          semester.stop AS semester_stop,
          semester.name AS semester_name
        FROM
          semester
        LEFT JOIN
          course ON (course.semester_id = semester.id)
        LEFT JOIN
          production_action ON (
            production_action.id = course.production_action_id)
        WHERE
          semester.teaching_period_id = ?
        ORDER BY
          production_action.name
    ''', (teaching_period_id,))
    production_actions = cursor.fetchall()
    cursor.execute(
        'SELECT id, name, code FROM production_action ORDER BY name')
    all_production_actions = cursor.fetchall()
    cursor.execute('''
        SELECT
          student.id,
          person.lastname || ' ' || person.firstname as name,
          person.mail,
          registration.id AS registration_id
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
    cursor.execute('''
        SELECT
          student.id,
          person.lastname || ' ' || person.firstname as name,
          person.mail
        FROM
          person
        JOIN
          student ON (student.person_id = person.id)
        ORDER BY
          person.lastname
    ''')
    all_students = cursor.fetchall()
    cursor.execute('''
        SELECT DISTINCT registration_id FROM tutoring UNION
        SELECT DISTINCT registration_id FROM tracking UNION
        SELECT DISTINCT registration_id FROM assignment UNION
        SELECT DISTINCT registration_id FROM examination_mark
    ''')
    registrations_with_data = tuple(
        registration['registration_id'] for registration in cursor.fetchall())
    return render_template(
        'teaching_period.jinja2.html', teaching_period=teaching_period,
        production_actions=production_actions, all_students=all_students,
        all_production_actions=all_production_actions, students=students,
        registrations_with_data=registrations_with_data)


@app.route('/teaching-period/add', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def teaching_period_add():
    if request.method == 'POST':
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute('''
            INSERT INTO teaching_period (code, name)
            VALUES (:code, :name)
        ''', request.form)
        connection.commit()
        flash('La période de formation a été ajoutée')
        return redirect(url_for('index'))
    return render_template('teaching_period_add.jinja2.html')


@app.route(
    '/teaching-period/delete/<int:teaching_period_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def teaching_period_delete(teaching_period_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        DELETE FROM teaching_period
        WHERE id = ?
    ''', (teaching_period_id,))
    connection.commit()
    flash('La période de formation a été supprimée')
    return redirect(url_for('index'))


@app.route('/registration/add-student/<int:student_id>', methods=('POST',))
@app.route('/registration/add/<int:teaching_period_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def registration_add(teaching_period_id=None, student_id=None):
    connection = get_connection()
    cursor = connection.cursor()
    if teaching_period_id is None:
        teaching_period_id = request.form['teaching_period_id']
    elif student_id is None:
        student_id = request.form['student_id']
    cursor.execute('''
        INSERT INTO registration (teaching_period_id, student_id)
        VALUES (?, ?)
    ''', (teaching_period_id, student_id))
    connection.commit()
    flash('L’apprenant a été inscrit')
    return redirect(request.referrer)


@app.route('/registration/delete/<int:registration_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def registration_delete(registration_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        DELETE FROM registration
        WHERE id = ?
    ''', (registration_id,))
    connection.commit()
    flash('L’apprenant a été désinscrit')
    return redirect(request.referrer)


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
            UPDATE production_action
            SET code = ?, name = ?, teacher_id = ?, last_course_date = ?
            WHERE production_action.id = ?
        ''', values)
        connection.commit()
        flash('L’action de production a été modifiée')
        return redirect(url_for(
            'production_action', production_action_id=production_action_id))
    cursor.execute('''
        SELECT id, code, name, teacher_id, last_course_date
        FROM production_action
        WHERE production_action.id = ?
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
    cursor.execute('''
        SELECT
          semester.id AS semester_id,
          semester.name AS semester_name,
          course.id AS course_id,
          teaching_period.name AS teaching_period_name,
          assignment.id AS assignment_id,
          registration.id AS registration_id,
          person.lastname || ' ' || person.firstname AS name,
          person.mail,
          student.id
        FROM
          course
        JOIN
          semester ON (semester.id = course.semester_id),
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        LEFT JOIN
          assignment ON (assignment.course_id = course.id)
        LEFT JOIN
          registration ON (registration.id = assignment.registration_id)
        LEFT JOIN
          student ON (student.id = registration.student_id)
        LEFT JOIN
          person ON (person.id = student.person_id)
        WHERE
          course.production_action_id = ?
        ORDER BY
          teaching_period.name,
          semester.name,
          person.lastname
    ''', (production_action_id,))
    students = cursor.fetchall()
    cursor.execute('''
        SELECT
          student.id,
          person.lastname || ' ' || person.firstname AS name,
          person.mail,
          registration.id AS registration_id
        FROM
          course
        JOIN
          semester ON (semester.id = course.semester_id),
          registration ON (
            semester.teaching_period_id = registration.teaching_period_id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        WHERE
          course.production_action_id = ?
        ORDER BY
          person.lastname
    ''', (production_action_id,))
    all_students = cursor.fetchall()
    cursor.execute('''
        SELECT
          semester.id,
          semester.name,
          teaching_period.name AS teaching_period_name
        FROM
          semester
        JOIN
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        ORDER BY
          teaching_period.name,
          semester.name
    ''')
    semesters = cursor.fetchall()
    return render_template(
        'production_action.jinja2.html', production_action=production_action,
        teachers=teachers, students=students, all_students=all_students,
        semesters=semesters)


@app.route('/production-action/add', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def production_action_add():
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            INSERT INTO
              production_action (teacher_id, code, name, last_course_date)
            VALUES
              (:teacher, :code, :name, :last_course_date)
        ''', request.form)
        connection.commit()
        flash('L’action de production a été ajoutée')
        return redirect(url_for('index'))
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
        'production_action_add.jinja2.html', teachers=teachers)


@app.route(
    '/production-action/link-teacher/<int:teacher_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def production_action_link_teacher(teacher_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        UPDATE production_action
        SET teacher_id = ?
        WHERE id = ?
    ''', (teacher_id, request.form['production_action_id']))
    connection.commit()
    flash('L’action de production a été assignée au formateur')
    return redirect(request.referrer)


@app.route(
    '/production-action/unlink-teacher/<int:production_action_id>',
    methods=('POST',))
@user.check(user.is_superadministrator)
def production_action_unlink_teacher(production_action_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        UPDATE production_action
        SET teacher_id = NULL
        WHERE id = ?
    ''', (production_action_id,))
    connection.commit()
    flash('L’action de production a été retirée au formateur')
    return redirect(request.referrer)


@app.route(
    '/production-action/delete/<int:production_action_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def production_action_delete(production_action_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        DELETE FROM production_action
        WHERE id = ?
    ''', (production_action_id,))
    connection.commit()
    flash('L’action de production a été supprimée')
    return redirect(url_for('index'))


@app.route(
    '/production-action/link-semester/<int:semester_id>', methods=('POST',))
@app.route(
    '/production-action/link/<int:production_action_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def production_action_link(semester_id=None, production_action_id=None):
    connection = get_connection()
    cursor = connection.cursor()
    if semester_id is None:
        semester_id = request.form['semester_id']
    elif production_action_id is None:
        production_action_id = request.form['production_action_id']
    cursor.execute('''
        INSERT INTO course (semester_id, production_action_id)
        VALUES (?, ?)
    ''', (semester_id, production_action_id))
    connection.commit()
    flash('L’action de production a été associée')
    return redirect(request.referrer)


@app.route('/production-action/unlink/<int:course_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def production_action_unlink(course_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        DELETE FROM course
        WHERE id = ?
    ''', (course_id,))
    connection.commit()
    flash('L’action de production a été dissociée')
    return redirect(request.referrer)


@app.route(
    '/course/link-registration/<int:registration_id>', methods=('POST',))
@app.route('/course/link/<int:course_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def course_link(course_id=None, registration_id=None):
    connection = get_connection()
    cursor = connection.cursor()
    if course_id is None:
        course_id = request.form['course_id']
    elif registration_id is None:
        registration_id = request.form['registration_id']
    cursor.execute('''
        INSERT INTO assignment (registration_id, course_id)
        VALUES (?, ?)
    ''', (registration_id, course_id))
    connection.commit()
    flash('L’apprenant a été inscrit')
    return redirect(request.referrer)


@app.route('/course/unlink/<int:assignment_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def course_unlink(assignment_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('DELETE FROM assignment WHERE id = ?', (assignment_id,))
    connection.commit()
    flash('L’apprenant a été désinscrit')
    return redirect(request.referrer)


@app.route('/semester/<int:semester_id>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def semester(semester_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            UPDATE semester
            SET name = ?, start = ?, stop = ?
            WHERE id = ?
            RETURNING teaching_period_id
        ''', (
            request.form['name'], request.form['start'], request.form['stop'],
            semester_id))
        teaching_period_id = cursor.fetchone()['teaching_period_id']
        connection.commit()
        flash('Les informations du semestre ont été mises à jour')
        return redirect(url_for(
            'teaching_period', teaching_period_id=teaching_period_id))
    cursor.execute('''
        SELECT
          semester.name,
          semester.start,
          semester.stop,
          teaching_period.name AS teaching_period_name
        FROM
          semester
        JOIN
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        WHERE
          semester.id = ?
    ''', (semester_id,))
    semester = cursor.fetchone()
    return render_template('semester.jinja2.html', semester=semester)


@app.route('/semester/add/<int:teaching_period_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def semester_add(teaching_period_id):
    connection = get_connection()
    cursor = connection.cursor()
    form = dict(request.form)
    form['teaching_period_id'] = teaching_period_id
    cursor.execute('''
        INSERT INTO semester (teaching_period_id, name, start, stop)
        VALUES (:teaching_period_id, :name, :start, :stop)
    ''', form)
    connection.commit()
    flash('Le semestre a été ajouté')
    return redirect(url_for(
        'teaching_period', teaching_period_id=teaching_period_id))


@app.route('/semester/delete/<int:semester_id>', methods=('POST',))
@user.check(user.is_superadministrator)
def semester_delete(semester_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        DELETE FROM semester
        WHERE id = ?
        RETURNING teaching_period_id
    ''', (semester_id,))
    teaching_period_id = cursor.fetchone()['teaching_period_id']
    connection.commit()
    flash('Le semestre a été supprimé')
    return redirect(url_for(
        'teaching_period', teaching_period_id=teaching_period_id))


@app.route('/mark/<int:assignment_id>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def mark(assignment_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            UPDATE assignment
            SET mark = ?, comments = ?
            WHERE id = ?
            RETURNING registration_id
        ''', (request.form['mark'], request.form['comments'], assignment_id))
        registration_id = cursor.fetchone()['registration_id']
        connection.commit()
        flash('La note a été modifiée')
        return redirect(url_for('report', registration_id=registration_id))
    cursor.execute('''
        SELECT
          assignment.mark,
          assignment.comments,
          teaching_period.name AS teaching_period_name,
          person.firstname || ' ' || person.lastname AS person_name
        FROM
          assignment
        JOIN
          registration ON (registration.id = assignment.registration_id),
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id),
          teaching_period ON (
            teaching_period.id = registration.teaching_period_id)
        WHERE
          assignment.id = ?
    ''', (assignment_id,))
    assignment = cursor.fetchone()
    return render_template('mark.jinja2.html', assignment=assignment)


@app.route(
    '/examination-mark/<int:examination_id>/<int:registration_id>',
    methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def examination_mark(examination_id, registration_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            INSERT INTO examination_mark (
              examination_id, registration_id, mark, comments)
            VALUES (?, ?, ?, ?)
        ''', (
            examination_id, registration_id,
            request.form['mark'], request.form['comments']))
        connection.commit()
        flash('La note a été modifiée')
        return redirect(url_for('report', registration_id=registration_id))
    cursor.execute('''
        SELECT
          mark,
          comments,
          examination.name,
          person.firstname || ' ' || person.lastname AS person_name
        FROM
          examination
        JOIN
          registration,
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        LEFT JOIN
          examination_mark ON (
            examination_mark.examination_id = examination.id AND
            examination_mark.registration_id = registration.id)
        WHERE
          examination.id = ? AND
          registration.id = ?
    ''', (examination_id, registration_id))
    examination_mark = cursor.fetchone()
    return render_template(
        'examination_mark.jinja2.html', examination_mark=examination_mark)


@app.route(
    '/semester-comment/<int:semester_id>/<int:registration_id>',
    methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def semester_comment(semester_id, registration_id):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        cursor.execute('''
            INSERT INTO tracking (semester_id, registration_id, comments)
            VALUES (?, ?, ?)
        ''', (semester_id, registration_id, request.form['comments']))
        connection.commit()
        flash('Le commentaire a été modifié')
        return redirect(url_for('report', registration_id=registration_id))
    cursor.execute('''
        SELECT
          semester.name,
          tracking.comments,
          person.firstname || ' ' || person.lastname AS person_name
        FROM
          semester
        JOIN
          registration,
          student ON (student.id = registration.student_id),
          person ON (person.id = student.person_id)
        LEFT JOIN
          tracking ON (
            tracking.semester_id = semester.id AND
            tracking.registration_id = registration.id)
        WHERE
          semester.id = ? AND
          registration.id = ?
    ''', (semester_id, registration_id))
    semester = cursor.fetchone()
    return render_template('semester_comment.jinja2.html', semester=semester)


@app.route('/absences/<int:registration_id>', methods=('GET', 'POST'))
@user.check(user.is_superadministrator)
def absences(registration_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT
          student.id,
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
    student = cursor.fetchone()
    cursor.execute('''
        SELECT
          semester.id AS semester_id,
          semester.name AS semester_name,
          tracking.justified_absence_minutes,
          tracking.unjustified_absence_minutes,
          tracking.lateness_minutes,
          tracking.comments AS tracking_comments
        FROM
          semester
        JOIN
          teaching_period ON (teaching_period.id = semester.teaching_period_id)
        JOIN
          registration ON (
            registration.teaching_period_id = teaching_period.id)
        LEFT JOIN
          tracking ON (tracking.semester_id = semester.id)
        WHERE
          registration.id = ?
        ORDER BY
          semester.start
    ''', (registration_id,))
    trackings = cursor.fetchall()
    if request.method == 'POST':
        for tracking in trackings:
            semester_id = tracking['semester_id']
            cursor.execute('''
                INSERT INTO tracking (
                  registration_id, semester_id, justified_absence_minutes,
                  unjustified_absence_minutes, lateness_minutes)
                VALUES
                  (?, ?, ?, ?, ?)
            ''', (
                registration_id, semester_id,
                request.form[f'justified_absence_minutes_{semester_id}'],
                request.form[f'unjustified_absence_minutes_{semester_id}'],
                request.form[f'lateness_minutes_{semester_id}'],
            ))
        connection.commit()
        flash('Les absences ont été modifiées')
        return redirect(url_for('report', registration_id=registration_id))
    return render_template(
        'absences.jinja2.html', student=student, trackings=trackings)


@app.route('/lost_password', methods=('GET', 'POST'))
def lost_password():
    if request.method == 'POST':
        connection = get_connection()
        cursor = connection.cursor()
        uuid = str(uuid4())
        cursor.execute('''
            UPDATE person
            SET reset_password = ?
            WHERE mail = ?
            RETURNING id, firstname, lastname
        ''', (uuid, request.form['mail'],))
        person = cursor.fetchone()
        connection.commit()
        if person:
            smtp = SMTP_SSL(app.config['SMTP_HOSTNAME'])
            smtp.set_debuglevel(1)
            smtp.login(app.config['SMTP_LOGIN'], app.config['SMTP_PASSWORD'])
            message = EmailMessage()
            message['From'] = app.config['SMTP_FROM']
            message['To'] = request.form['mail']
            message['Subject'] = 'Réinitialisation de mot de passe'
            message.set_content(
                f'Bonjour {person["firstname"]} {person["lastname"]},\n\n'
                'Nous avons reçu une demande de réinitialisation de mot de '
                'passe concernant votre compte IPI. Merci de vous rendre '
                'sur l’adresse suivante pour changer votre mot de passe :\n\n'
                f'{url_for("reset_password", uuid=uuid, _external=True)}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, vous pouvez '
                'ignorer ce message.'
            )
            smtp.send_message(message)
            smtp.quit()
        flash('Un message vous a été envoyé si votre email est correct')
        return redirect(url_for('login'))
    return render_template('lost_password.jinja2.html')


@app.route('/reset_password/<uuid>', methods=('GET', 'POST'))
def reset_password(uuid):
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        password_match = (
            request.form.get('password') ==
            request.form.get('confirm_password'))
        if not password_match:
            flash('Les deux mots de passe doivent être les mêmes')
            return redirect(request.referrer)
        cursor.execute('''
            UPDATE person
            SET password = ?, reset_password = NULL
            WHERE reset_password = ?
        ''', (generate_password_hash(request.form['password']), uuid))
        connection.commit()
        flash('Le mot de passe a été modifié, merci de vous connecter')
        return redirect(url_for('login'))
    return render_template('reset_password.jinja2.html')


@app.template_filter()
def hours(minutes):
    minutes = minutes or 0
    return (
        f'{minutes} min' if minutes < 60 else
        f'{minutes//60} h {minutes%60:02}')


@app.template_filter()
def float(number):
    return str(number).replace('.', ',')


@app.template_filter()
def date(iso_date):
    return '/'.join(iso_date.split('-')[::-1])


@app.context_processor
def inject_variables():
    return {'user': user}


@app.teardown_appcontext
def teardown(exception):
    close_connection()
