CREATE TABLE person (
  mail TEXT UNIQUE NOT NULL,
  civility TEXT NOT NULL,
  lastname TEXT NOT NULL,
  firstname TEXT NOT NULL,
  password TEXT,
  photo BLOB
);

CREATE TABLE tutor (
  person_id INTEGER NOT NULL REFERENCES person(rowid),
  company TEXT
);

CREATE TABLE teacher (
  person_id INTEGER NOT NULL REFERENCES person(rowid)
);

CREATE TABLE student (
  person_id INTEGER NOT NULL REFERENCES person(rowid)
);

CREATE TABLE administrator (
  person_id INTEGER NOT NULL REFERENCES person(rowid)
);

CREATE TABLE superadministrator (
  person_id INTEGER NOT NULL REFERENCES person(rowid)
);

CREATE TABLE teaching_period (
  name TEXT NOT NULL
);

CREATE TABLE registration (
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(rowid),
  student_id INTEGER NOT NULL REFERENCES student(rowid)
);

CREATE TABLE tutoring (
  tutor_id INTEGER NOT NULL REFERENCES tutor(rowid),
  registration_id INTEGER NOT NULL REFERENCES registration(rowid)
);

CREATE TABLE semester (
  teaching_period_id INTEGER NOT NULL REFERENCES teaching_period(rowid),
  start DATE NOT NULL,
  stop DATE NOT NULL
);

CREATE TABLE tracking (
  registration_id INTEGER NOT NULL REFERENCES registration(rowid),
  semester_id INTEGER NOT NULL REFERENCES semester(rowid),
  justified_absence_minutes INTEGER NOT NULL,
  unjustified_absence_minutes INTEGER NOT NULL,
  lateness_minutes INTEGER NOT NULL,
  comments TEXT
);

CREATE TABLE production_action (
  teacher_id INTEGER NOT NULL REFERENCES teacher(rowid),
  last_course_date DATE
);

CREATE TABLE course (
  semester_id INTEGER NOT NULL REFERENCES semester(rowid),
  production_action_id INTEGER NOT NULL REFERENCES production_action(rowid)
);

CREATE TABLE assignment (
  registration_id INTEGER NOT NULL REFERENCES registration(rowid),
  course_id INTEGER NOT NULL REFERENCES course(rowid),
  mark TEXT,
  comments TEXT
);
