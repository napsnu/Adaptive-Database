BEGIN;
--
-- Add field suggested_unit_order to topic
--
ALTER TABLE "assessment_topic" ADD COLUMN "suggested_unit_order" integer unsigned NULL CHECK ("suggested_unit_order" >= 0);
--
-- Create model AnswerSample
--
CREATE TABLE "assessment_answersample" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "text" text NOT NULL, "keywords" text NOT NULL CHECK ((JSON_VALID("keywords") OR "keywords" IS NULL)), "weight" real NOT NULL, "order" integer unsigned NOT NULL CHECK ("order" >= 0), "question_id" bigint NOT NULL REFERENCES "assessment_question" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model CEFRSubLevel
--
CREATE TABLE "assessment_cefrsublevel" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "code" varchar(10) NOT NULL UNIQUE, "unit_order" integer unsigned NOT NULL CHECK ("unit_order" >= 0), "title" varchar(150) NOT NULL, "description" text NOT NULL, "is_active" bool NOT NULL, "cefr_level_id" bigint NOT NULL REFERENCES "assessment_cefrlevel" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Add field current_sublevel to assessmentsession
--
ALTER TABLE "assessment_assessmentsession" ADD COLUMN "current_sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Add field final_sublevel to assessmentsession
--
ALTER TABLE "assessment_assessmentsession" ADD COLUMN "final_sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Add field starting_sublevel to assessmentsession
--
ALTER TABLE "assessment_assessmentsession" ADD COLUMN "starting_sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Add field current_sublevel to candidate
--
ALTER TABLE "assessment_candidate" ADD COLUMN "current_sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Add field sublevel to question
--
ALTER TABLE "assessment_question" ADD COLUMN "sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Create model UserAttempt
--
CREATE TABLE "assessment_userattempt" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "submitted_answer" text NOT NULL, "is_correct" bool NOT NULL, "score" real NOT NULL, "max_score" real NOT NULL, "attempt_no" integer unsigned NOT NULL CHECK ("attempt_no" >= 0), "created_at" datetime NOT NULL, "candidate_id" bigint NOT NULL REFERENCES "assessment_candidate" ("id") DEFERRABLE INITIALLY DEFERRED, "cefr_level_id" bigint NOT NULL REFERENCES "assessment_cefrlevel" ("id") DEFERRABLE INITIALLY DEFERRED, "question_id" bigint NOT NULL REFERENCES "assessment_question" ("id") DEFERRABLE INITIALLY DEFERRED, "session_id" char(32) NOT NULL REFERENCES "assessment_assessmentsession" ("id") DEFERRABLE INITIALLY DEFERRED, "skill_id" bigint NOT NULL REFERENCES "assessment_skill" ("id") DEFERRABLE INITIALLY DEFERRED, "sublevel_id" bigint NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED);
--
-- Create model UserProgress
--
CREATE TABLE "assessment_userprogress" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "questions_answered" integer unsigned NOT NULL CHECK ("questions_answered" >= 0), "correct_answers" integer unsigned NOT NULL CHECK ("correct_answers" >= 0), "attempts" integer unsigned NOT NULL CHECK ("attempts" >= 0), "mastery_score" real NOT NULL, "is_unlocked" bool NOT NULL, "is_completed" bool NOT NULL, "last_attempt_at" datetime NULL, "candidate_id" bigint NOT NULL REFERENCES "assessment_candidate" ("id") DEFERRABLE INITIALLY DEFERRED, "cefr_level_id" bigint NOT NULL REFERENCES "assessment_cefrlevel" ("id") DEFERRABLE INITIALLY DEFERRED, "skill_id" bigint NOT NULL REFERENCES "assessment_skill" ("id") DEFERRABLE INITIALLY DEFERRED, "sublevel_id" bigint NOT NULL REFERENCES "assessment_cefrsublevel" ("id") DEFERRABLE INITIALLY DEFERRED);
CREATE INDEX "assessment_answersample_question_id_6cb9d16a" ON "assessment_answersample" ("question_id");
CREATE UNIQUE INDEX "assessment_cefrsublevel_cefr_level_id_unit_order_c5536b50_uniq" ON "assessment_cefrsublevel" ("cefr_level_id", "unit_order");
CREATE INDEX "assessment_cefrsublevel_cefr_level_id_24a8fd32" ON "assessment_cefrsublevel" ("cefr_level_id");
CREATE INDEX "assessment_assessmentsession_current_sublevel_id_42040571" ON "assessment_assessmentsession" ("current_sublevel_id");
CREATE INDEX "assessment_assessmentsession_final_sublevel_id_fb0256c3" ON "assessment_assessmentsession" ("final_sublevel_id");
CREATE INDEX "assessment_assessmentsession_starting_sublevel_id_90f05dbe" ON "assessment_assessmentsession" ("starting_sublevel_id");
CREATE INDEX "assessment_candidate_current_sublevel_id_17e60f00" ON "assessment_candidate" ("current_sublevel_id");
CREATE INDEX "assessment_question_sublevel_id_837b4c29" ON "assessment_question" ("sublevel_id");
CREATE INDEX "assessment_userattempt_candidate_id_c672cd35" ON "assessment_userattempt" ("candidate_id");
CREATE INDEX "assessment_userattempt_cefr_level_id_8e0d4e22" ON "assessment_userattempt" ("cefr_level_id");
CREATE INDEX "assessment_userattempt_question_id_13ffc14f" ON "assessment_userattempt" ("question_id");
CREATE INDEX "assessment_userattempt_session_id_370600fa" ON "assessment_userattempt" ("session_id");
CREATE INDEX "assessment_userattempt_skill_id_283a4333" ON "assessment_userattempt" ("skill_id");
CREATE INDEX "assessment_userattempt_sublevel_id_11c3c422" ON "assessment_userattempt" ("sublevel_id");
CREATE UNIQUE INDEX "assessment_userprogress_candidate_id_sublevel_id_skill_id_bf92e7dc_uniq" ON "assessment_userprogress" ("candidate_id", "sublevel_id", "skill_id");
CREATE INDEX "assessment_userprogress_candidate_id_da4028f8" ON "assessment_userprogress" ("candidate_id");
CREATE INDEX "assessment_userprogress_cefr_level_id_455482ab" ON "assessment_userprogress" ("cefr_level_id");
CREATE INDEX "assessment_userprogress_skill_id_d91d0bf1" ON "assessment_userprogress" ("skill_id");
CREATE INDEX "assessment_userprogress_sublevel_id_eb4a19eb" ON "assessment_userprogress" ("sublevel_id");
COMMIT;
