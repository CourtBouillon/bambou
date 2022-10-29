PRAGMA foreign_keys=ON;

CREATE TABLE person (
  id INTEGER PRIMARY KEY,
  mail TEXT UNIQUE NOT NULL,
  civility TEXT,
  firstname TEXT NOT NULL,
  lastname TEXT NOT NULL,
  password TEXT,
  photo BLOB
);

CREATE TABLE tutor (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  company TEXT
);

CREATE TABLE teacher (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id)
);

CREATE TABLE student (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id)
);

CREATE TABLE administrator (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id)
);

CREATE TABLE superadministrator (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id)
);

CREATE TABLE teaching_period (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL
);

CREATE TABLE registration (
  id INTEGER PRIMARY KEY,
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(id),
  student_id INTEGER NOT NULL REFERENCES student(id)
);

CREATE TABLE tutoring (
  id INTEGER PRIMARY KEY,
  tutor_id INTEGER NOT NULL REFERENCES tutor(id),
  registration_id INTEGER NOT NULL REFERENCES registration(id)
);

CREATE TABLE semester (
  id INTEGER PRIMARY KEY,
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(id),
  name TEXT NOT NULL,
  start DATE NOT NULL,
  stop DATE NOT NULL
);

CREATE TABLE tracking (
  id INTEGER PRIMARY KEY,
  registration_id INTEGER NOT NULL REFERENCES registration(id),
  semester_id INTEGER NOT NULL REFERENCES semester(id),
  justified_absence_minutes INTEGER NOT NULL,
  unjustified_absence_minutes INTEGER NOT NULL,
  lateness_minutes INTEGER NOT NULL,
  comments TEXT
);

CREATE TABLE production_action (
  id INTEGER PRIMARY KEY,
  teacher_id INTEGER REFERENCES teacher(id),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  last_course_date DATE
);

CREATE TABLE course (
  id INTEGER PRIMARY KEY,
  semester_id INTEGER NOT NULL REFERENCES semester(id),
  production_action_id INTEGER NOT NULL REFERENCES production_action(id)
);

CREATE TABLE assignment (
  id INTEGER PRIMARY KEY,
  registration_id INTEGER NOT NULL REFERENCES registration(id),
  course_id INTEGER NOT NULL REFERENCES course(id),
  mark TEXT,
  comments TEXT
);

CREATE TABLE examination (
  id INTEGER PRIMARY KEY,
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(id),
  name TEXT
);

CREATE TABLE examination_mark (
  id INTEGER PRIMARY KEY,
  examination_id INTEGER NOT NULL REFERENCES examination(id),
  registration_id INTEGER NOT NULL REFERENCES registration(id),
  mark FLOAT,
  comment TEXT
);
