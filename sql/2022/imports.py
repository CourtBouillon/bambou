import csv
import sqlite3
from itertools import chain
from pathlib import Path
from unicodedata import normalize

_ignored_teachers = [
    '',
    'centre de ressources cdr',
    'cdr cdr',
    'centre de ressources',
    'berger amélie',
    'billard hélèna',
    'griol gael',
    'boisson thomas',
    'ipi lyon ipi lyon',
    'iltc',
]
_alias_teachers = {
    'berger': 'BERGER Amélie',
    'berger amelie': 'BERGER Amélie',
}


def slugify(text):
    return (
        normalize('NFKD', text).encode('ASCII', 'ignore')
        .decode().strip().lower())


connection = sqlite3.connect(Path(__file__).parent.parent / 'bambou.db')
cursor = connection.cursor()

actions = {}
periods = {}
students = {}
teachers = {}
tutors = {}

students_mails = {}
teachers_mails = {}
tutors_companies = {}

courses = set()
registrations = set()
assignments = set()

reader = csv.reader((Path(__file__).parent / 'students.csv').open())
next(reader)  # Remove header
for line in reader:
    person_id, mail = line[2], line[11]
    students_mails[person_id] = mail

reader = csv.reader((Path(__file__).parent / 'teachers.csv').open())
next(reader)  # Remove header
for line in reader:
    lastname, firstname, mail, igs_mail = line[0:4]
    teachers_mails[slugify(f'{lastname} {firstname}')] = mail or igs_mail

reader = csv.reader((Path(__file__).parent / 'students_modules.csv').open())
next(reader)  # Remove header
for line in reader:
    action_code, action_name, _, action_start, action_stop, code = line[2:8]
    for start in ('IAPI', 'IAPC', 'GEN', 'IZEX'):
        if code.startswith(start):
            continue
    person_id, civility, firstname, lastname = line[14:18]
    period_code, period_name = line[18:]
    mail = students_mails[person_id]
    if action_code not in actions:
        actions[action_code] = action_name
    if period_code not in periods:
        periods[period_code] = period_name
    if person_id not in students:
        students[person_id] = (firstname, lastname, mail)
    courses.add((period_code, action_code))
    registrations.add((period_code, mail))
    assignments.add((period_code, action_code, mail))

reader = csv.reader((Path(__file__).parent / 'tutors.csv').open())
next(reader)  # Remove header
for i, line in enumerate(reader):
    student_lastname, student_firstname = line[3:5]
    company, tutor_lastname, tutor_firstname, tutor_mail = line[5:9]
    tutors[(student_lastname, student_firstname)] = (
        tutor_lastname, tutor_firstname, tutor_mail)
    tutors_companies[tutor_mail] = company

reader = csv.reader((Path(__file__).parent / 'courses.csv').open())
next(reader)  # Remove header
for line in reader:
    period_code, _, action_code = line[8:11]
    teacher = _alias_teachers.get(line[16].lower(), line[16])
    if slugify(teacher) in _ignored_teachers:
        if action_code not in teachers:
            teachers[action_code] = set()
    else:
        teachers.setdefault(action_code, set()).add(teacher)

for code, teacher in teachers.copy().items():
    if len(teacher) == 0:
        teachers[code] = None
    else:
        if len(set(teacher.lower() for teacher in teacher)) > 1:
            print('Plusieurs enseignants', code, teacher)
        teachers[code] = teacher.pop()

slugs = set(slugify(teacher) for teacher in teachers.values() if teacher)
for slug in slugs:
    if slug not in _ignored_teachers and slug not in teachers_mails:
        print('Email enseignant manquant', slug)
teacher_names = tuple({(
    teacher.rsplit(' ', 1)[0].upper(),
    teacher.rsplit(' ', 1)[1].title(),
    teachers_mails.get(slugify(teacher), f'{slugify(teacher)}@example.com'))
    for teacher in teachers.values() if teacher})
action_teachers = tuple(
    (action_code, teachers_mails.get(
        slugify(teacher), f'{slugify(teacher)}@example.com'))
    for action_code, teacher in teachers.items() if teacher)

cursor.execute('PRAGMA foreign_keys=ON')

request = 'INSERT INTO production_action (code, name) VALUES '
request += ', '.join(('(?, ?)',) * len(actions))
cursor.execute(request, tuple(chain(*actions.items())))

request = 'INSERT INTO teaching_period (code, name) VALUES '
request += ', '.join(('(?, ?)',) * len(periods))
cursor.execute(request, tuple(chain(*periods.items())))

request = 'INSERT INTO semester (teaching_period_id, name, start, stop) VALUES'
request += ', '.join(
    ("(?, 'Semestre 1', '2022-09-01', '2023-02-28')",) * len(periods))
cursor.execute(request, tuple(range(1, len(periods) + 1)))

request = 'INSERT INTO person (lastname, firstname, mail) VALUES '
request += ', '.join(('(?, ?, ?)',) * (
    len(teacher_names) + len(students) + len(set(tutors.values()))))
cursor.execute(request, tuple(chain(
    *teacher_names, *students.values(), *set(tutors.values()))))

request = 'INSERT INTO teacher (person_id) VALUES '
request += ', '.join(('(?)',) * len(teacher_names))
cursor.execute(request, tuple(range(1, len(teacher_names) + 1)))

request = 'INSERT INTO student (person_id) VALUES '
request += ', '.join(('(?)',) * len(students))
cursor.execute(request, tuple(range(
    len(teacher_names) + 1, len(teacher_names) + len(students) + 1)))

tutors_ids = {}
for _, _, mail in set(tutors.values()):
    company = tutors_companies[mail]
    request = '''
    INSERT INTO tutor (person_id, company)
    SELECT id, ?
    FROM person
    WHERE mail = ?
    RETURNING id
    '''
    cursor.execute(request, (company, mail))
    tutors_ids[mail] = cursor.fetchone()[0]

request = '''
    INSERT INTO course (semester_id, production_action_id)
    SELECT semester.id, production_action.id
    FROM teaching_period, production_action
    JOIN semester ON (semester.teaching_period_id = teaching_period.id)
    WHERE (teaching_period.code, production_action.code) IN ('''
request += ', '.join(('(?, ?)',) * len(courses)) + ')'
cursor.execute(request, tuple(chain(*courses)))

request = '''
    INSERT INTO registration (teaching_period_id, student_id)
    SELECT teaching_period.id, student.id
    FROM teaching_period, student
    JOIN person ON (person.id = student.person_id)
    WHERE (teaching_period.code, person.mail) IN ('''
request += ', '.join(('(?, ?)',) * len(registrations)) + ')'
cursor.execute(request, tuple(chain(*registrations)))

for student, (_, _, mail) in tutors.items():
    tutor_id = tutors_ids[mail]
    cursor.execute(
        'SELECT id FROM person '
        'WHERE lastname LIKE ? and firstname LIKE ?', student)
    result = cursor.fetchone()
    if result:
        cursor.execute(
            'INSERT INTO tutoring (tutor_id, registration_id) '
            'SELECT ?, registration.id '
            'FROM registration '
            'JOIN student ON (student.id = registration.student_id) '
            'WHERE person_id = ? '
            'RETURNING id', (tutor_id, result[0]))
        lines = len(cursor.fetchall())
        if lines != 1:
            print('Problème de tuteur', f'({lines})', ' '.join(student))
    else:
        print('Tuteur non assigné', ' '.join(student))

request = '''
    INSERT INTO assignment (registration_id, course_id)
    SELECT registration.id, course.id
    FROM registration, course
    JOIN student ON (student.id = registration.student_id)
    JOIN person ON (person.id = student.person_id)
    JOIN semester ON (semester.id = course.semester_id)
    JOIN teaching_period
      ON (teaching_period.id = semester.teaching_period_id)
    JOIN production_action
      ON (production_action.id = course.production_action_id)
    WHERE (teaching_period.code, production_action.code, person.mail) IN ('''
request += ', '.join(('(?, ?, ?)',) * len(assignments)) + ')'
cursor.execute(request, tuple(chain(*assignments)))

request = '''
    UPDATE production_action
    SET teacher_id = teacher.id
    FROM teacher JOIN person ON (teacher.person_id = person.id)
    WHERE (production_action.code, person.mail) IN ('''
request += ', '.join(('(?, ?)',) * len(action_teachers)) + ')'
cursor.execute(request, tuple(chain(*action_teachers)))

connection.commit()
