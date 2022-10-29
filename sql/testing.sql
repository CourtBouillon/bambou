INSERT INTO person (mail, civility, firstname, lastname)
VALUES
  ('marie@apprenant.fr', 'Mme', 'Marie', 'Étudiante'),
  ('gerard@admin.fr', 'M.', 'Gérard', 'Admin'),
  ('lucie@superadmin.com', 'Mme', 'Lucie', 'Superadmin'),
  ('guillaume@prof.fr', 'M.', 'Guillaume', 'Enseignant'),
  ('camille@tuteur.fr', 'Mme', 'Camille', 'Tutrice');

INSERT INTO tutor (person_id, company)
VALUES
  (5, 'Entreprise.corp');

INSERT INTO teacher (person_id)
VALUES
  (4);

INSERT INTO student (person_id)
VALUES
  (1);

INSERT INTO administrator (person_id)
VALUES
  (2);

INSERT INTO superadministrator (person_id)
VALUES
  (3);

INSERT INTO teaching_period (code, name)
VALUES
  ('12345', 'CDEV 2022/2023');

INSERT INTO registration (teaching_period_id, student_id)
VALUES
  (1, 1);

INSERT INTO tutoring (tutor_id, registration_id)
VALUES
  (1, 1);

INSERT INTO semester (teaching_period_id, name, start, stop)
VALUES
  (1, 'Semestre 1', '2022-09-01', '2023-02-28'),
  (1, 'Semestre 2', '2023-03-01', '2023-08-31');

INSERT INTO tracking (registration_id, semester_id, justified_absence_minutes, unjustified_absence_minutes, lateness_minutes, comments)
VALUES
  (1, 1, 30, 45, 15, 'Pas trop mal'),
  (1, 2, 0, 900, 150, 'Trop nul');

INSERT INTO production_action (teacher_id, code, name)
VALUES
  (1, 'CD93837', 'Python CDEV 2022/2023');

INSERT INTO course (semester_id, production_action_id)
VALUES
  (1, 1);

INSERT INTO assignment (registration_id, course_id, mark, comments)
VALUES
  (1, 1, 'A', 'Très bien !');

INSERT INTO examination (teaching_period_id, name)
VALUES
  (1, 'Examen 1');

INSERT INTO examination_mark (examination_id, registration_id, mark, comment)
VALUES
  (1, 1, 17.5, 'Très bon travail');
