import csv
import sqlite3
from itertools import chain
from pathlib import Path

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

connection = sqlite3.connect(Path(__file__).parent.parent / 'bambou.db')
cursor = connection.cursor()

actions = {}
periods = {}
students = {}
teachers = {}
courses = set()
registrations = set()
assignments = set()

reader = csv.reader((Path(__file__).parent / 'apprenants_modules.csv').open())
next(reader)  # Remove header
for line in reader:
    action_code, action_name, _, action_start, action_stop = line[2:7]
    person_id, civility, firstname, lastname = line[14:18]
    period_code, period_name = line[18:]
    if action_code not in actions:
        actions[action_code] = action_name
    if period_code not in periods:
        periods[period_code] = period_name
    if person_id not in students:
        students[person_id] = (firstname, lastname, f'{person_id}@ipilyon.net')
    courses.add((period_code, action_code))
    registrations.add((period_code, f'{person_id}@ipilyon.net'))
    assignments.add((period_code, action_code, f'{person_id}@ipilyon.net'))

reader = csv.reader((Path(__file__).parent / 'cours.csv').open())
next(reader)  # Remove header
for line in reader:
    period_code, _, action_code = line[8:11]
    teacher = _alias_teachers.get(line[16].lower(), line[16])
    if teacher.lower() in _ignored_teachers:
        if action_code not in teachers:
            teachers[action_code] = set()
    else:
        teachers.setdefault(action_code, set()).add(teacher)

for code, teacher in teachers.copy().items():
    if len(teacher) == 0:
        teachers[code] = None
    else:
        if len(set(teacher.lower() for teacher in teacher)) > 1:
            print('Problème d’enseignant :', code, teacher)
        teachers[code] = teacher.pop()

teacher_names = tuple({(
    teacher.rsplit(' ', 1)[0].upper(),
    teacher.rsplit(' ', 1)[1].title(),
    f'{teacher.lower().replace(" ", ".")}@test.com')
    for teacher in teachers.values() if teacher})
action_teachers = tuple(
    (action_code, f'{teacher.lower().replace(" ", ".")}@test.com')
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
request += ', '.join(
    ('(?, ?, ?)',) * (len(teacher_names) + len(students)))
cursor.execute(request, tuple(chain(*teacher_names, *students.values())))

request = 'INSERT INTO teacher (person_id) VALUES '
request += ', '.join(('(?)',) * len(teacher_names))
cursor.execute(request, tuple(range(1, len(teacher_names) + 1)))

request = 'INSERT INTO student (person_id) VALUES '
request += ', '.join(('(?)',) * len(students))
cursor.execute(request, tuple(range(
    len(teacher_names) + 1, len(teacher_names) + len(students) + 1)))

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
