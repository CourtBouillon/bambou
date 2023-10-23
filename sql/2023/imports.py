import csv
import sqlite3
from itertools import batched, chain
from pathlib import Path

actions = {}  # code: name
periods = {}  # code: name
teacher_names = []  # lastname, firstname, mail
students = {}  # code: lastname, firstname, mail
tutors = {}  # st_lastname, st_firstname: lastname, firstname, mail, company
courses = set()  # teaching_period_code, production_action_code
registrations = set()  # teaching_period_code, student_mail
assignments = set()  # teaching_period_code, production_action_code, st_mail
# action_teachers = []  # production_action_code, teacher_mail

reader = csv.reader((Path(__file__).parent / 'students.csv').open())
next(reader)  # Remove header
for line in reader:
    if line[6].endswith('2023'):
        continue

    action_code, action_name = line[2:4]
    actions[action_code] = action_name

    period_code, period_name = line[-2:]
    periods[period_code] = period_name

    id, _, lastname, firstname, mail = line[14:19]
    students[id] = (lastname, firstname, mail)

    courses.add((period_code, action_code))

    registrations.add((period_code, mail))

    assignments.add((period_code, action_code, mail))

reader = csv.reader((Path(__file__).parent / 'tutors.csv').open())
next(reader)  # Remove header
for line in reader:
    company, lastname, firstname, mail = line[5:]
    if all(line[5:]):
        tutors[tuple(line[3:5])] = (lastname, firstname, mail, company)

reader = csv.reader((Path(__file__).parent / 'tutors.csv').open())
next(reader)  # Remove header
for line in reader:
    teacher_names.append(line[:3])


connection = sqlite3.connect(Path(__file__).parent.parent.parent / 'bambou.db')
cursor = connection.cursor()

cursor.execute('ALTER TABLE registration RENAME TO registration_old')
cursor.execute('''
CREATE TABLE registration (
  id INTEGER PRIMARY KEY,
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(id),
  student_id INTEGER NOT NULL REFERENCES student(id),
  CONSTRAINT registration_unique UNIQUE (teaching_period_id, student_id)
)''')
cursor.execute('INSERT INTO registration SELECT * FROM registration_old')
cursor.execute('DROP TABLE registration_old')

cursor.execute('ALTER TABLE tutoring RENAME TO tutoring_old')
cursor.execute('''
CREATE TABLE tutoring (
  id INTEGER PRIMARY KEY,
  tutor_id INTEGER NOT NULL REFERENCES tutor(id),
  registration_id INTEGER NOT NULL REFERENCES registration(id),
  CONSTRAINT tutoring_unique UNIQUE (tutor_id, registration_id)
)''')
cursor.execute('INSERT INTO tutoring SELECT * FROM tutoring_old')
cursor.execute('DROP TABLE tutoring_old')

cursor.execute('PRAGMA foreign_keys=ON')

cursor.execute(
    'ALTER TABLE teaching_period ADD COLUMN archived BOOLEAN DEFAULT false')
cursor.execute(
    'UPDATE teaching_period SET archived = true WHERE name NOT LIKE ?',
    ('%24%',))

request = 'INSERT INTO production_action (code, name) VALUES '
request += ', '.join(('(?, ?)',) * len(actions))
request += 'ON CONFLICT DO NOTHING'
cursor.execute(request, tuple(chain(*actions.items())))

ids = []
for code, name in periods.items():
    request = 'INSERT INTO teaching_period (code, name) VALUES (?, ?) '
    request += 'ON CONFLICT DO UPDATE SET name = ?, archived = false '
    request += 'RETURNING id'
    cursor.execute(request, (code, name, name))
    ids.append(cursor.fetchone()[0])

request = 'INSERT INTO semester (teaching_period_id, name, start, stop) VALUES'
request += ', '.join((
    "(?, 'Semestre ' || "
    "(select count(*) + 1 from semester where teaching_period_id = ?), "
    "'2023-09-01', '2024-02-28')",) * len(ids))
cursor.execute(request, tuple(chain(*zip(ids, ids))))

request = 'INSERT INTO person (lastname, firstname, mail) VALUES '
request += ', '.join(('(?, ?, ?)',) * (
    len(teacher_names) + len(students) + len(set(tutors.values()))))
request += 'ON CONFLICT DO UPDATE SET mail = mail '
request += 'RETURNING id'
cursor.execute(request, tuple(chain(
    *teacher_names, *students.values(),
    *set(tutor[:3] for tutor in tutors.values()))))
ids = tuple(chain(*cursor.fetchall()))

request = 'INSERT INTO teacher (person_id) VALUES '
request += ', '.join(('(?)',) * len(teacher_names))
request += 'ON CONFLICT DO NOTHING '
cursor.execute(request, ids[:len(teacher_names)])

request = 'INSERT INTO student (person_id) VALUES '
request += ', '.join(('(?)',) * len(students))
request += 'ON CONFLICT DO NOTHING '
cursor.execute(
    request, ids[len(teacher_names):len(teacher_names) + len(students)])

tutors_ids = {}
for _, _, mail, company in set(tutors.values()):
    request = '''
    INSERT INTO tutor (person_id, company)
    SELECT id, ?
    FROM person
    WHERE mail = ?
    ON CONFLICT DO UPDATE SET company = ?
    RETURNING id
    '''
    cursor.execute(request, (company, mail, company))
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
request += 'ON CONFLICT DO NOTHING'
cursor.execute(request, tuple(chain(*registrations)))

for student, (_, _, mail, _) in tutors.items():
    tutor_id = tutors_ids[mail]
    cursor.execute(
        'SELECT id FROM person '
        'WHERE lastname LIKE ? AND firstname LIKE ?', student)
    result = cursor.fetchone()
    if result:
        cursor.execute('''
            INSERT INTO tutoring (tutor_id, registration_id)
            SELECT ?, registration.id
            FROM registration
            JOIN student ON (student.id = registration.student_id)
            JOIN teaching_period ON (
              teaching_period.id = registration.teaching_period_id)
            WHERE person_id = ? AND teaching_period.archived = false
            ON CONFLICT DO UPDATE SET tutor_id = tutor_id
            RETURNING id''', (tutor_id, result[0]))
        lines = len(cursor.fetchall())
        if lines != 1:
            print('Problème de tuteur', f'({lines})', ' '.join(student))
    else:
        print('Tuteur non assigné', ' '.join(student))

for batch in batched(assignments, 5000):
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
        WHERE (teaching_period.code, production_action.code, person.mail)
        IN ('''
    request += ', '.join(('(?, ?, ?)',) * len(batch)) + ')'
    cursor.execute(request, tuple(chain(*batch)))

# request = '''
#     UPDATE production_action
#     SET teacher_id = teacher.id
#     FROM teacher JOIN person ON (teacher.person_id = person.id)
#     WHERE (production_action.code, person.mail) IN ('''
# request += ', '.join(('(?, ?)',) * len(action_teachers)) + ')'
# cursor.execute(request, tuple(chain(*action_teachers)))

connection.commit()
