from django.test import TestCase

from assessment.adaptive_engine import AdaptiveEngine
from assessment.models import (
	DifficultyTier,
	CEFRLevel,
	CEFRSubLevel,
	Skill,
	QuestionType,
	Topic,
	Question,
	QuestionOption,
	Candidate,
)


class AdaptiveEngineTests(TestCase):
	def setUp(self):
		self.level_a1, _ = CEFRLevel.objects.update_or_create(
			code='A1', defaults={'name': 'Breakthrough', 'order': 1}
		)
		self.beginner_tier, _ = DifficultyTier.objects.update_or_create(
			code='beginner',
			defaults={'name': 'Beginner', 'order': 1, 'grade_band': '4-5'},
		)

		self.level_a2, _ = CEFRLevel.objects.update_or_create(
			code='A2', defaults={'name': 'Waystage', 'order': 2}
		)

		self.sub_a11, _ = CEFRSubLevel.objects.update_or_create(
			cefr_level=self.level_a1,
			unit_order=1,
			defaults={
				'code': 'A1.1',
				'title': 'Unit 1',
				'is_active': True,
			},
		)
		self.sub_a12, _ = CEFRSubLevel.objects.update_or_create(
			cefr_level=self.level_a1,
			unit_order=2,
			defaults={
				'code': 'A1.2',
				'title': 'Unit 2',
				'is_active': True,
			},
		)

		self.reading, _ = Skill.objects.update_or_create(code='reading', defaults={'name': 'Reading', 'order': 1})
		self.writing, _ = Skill.objects.update_or_create(code='writing', defaults={'name': 'Writing', 'order': 2})
		self.listening, _ = Skill.objects.update_or_create(code='listening', defaults={'name': 'Listening', 'order': 3})
		self.speaking, _ = Skill.objects.update_or_create(code='speaking', defaults={'name': 'Speaking', 'order': 4})

		self.mcq, _ = QuestionType.objects.update_or_create(
			code='multiple_choice',
			defaults={
				'name': 'Multiple Choice',
				'response_format': 'single_choice',
				'is_auto_gradable': True,
			},
		)
		self.text_input, _ = QuestionType.objects.update_or_create(
			code='fill_in_the_blank',
			defaults={
				'name': 'Fill In',
				'response_format': 'text_input',
				'is_auto_gradable': True,
			},
		)

		self.topic, _ = Topic.objects.update_or_create(code='test_a1_topic', defaults={'name': 'Topic A1'})
		self.topic.cefr_levels.add(self.level_a1)

		self.candidate, _ = Candidate.objects.update_or_create(
			email='test@example.com',
			defaults={
				'name': 'Test User',
				'current_cefr_level': self.level_a1,
				'current_sublevel': self.sub_a11,
			},
		)

	def _create_mcq_question(self, idx):
		q = Question.objects.create(
			question_id=f'TEST-A1-R-{idx:03d}',
			cefr_level=self.level_a1,
			sublevel=self.sub_a11,
			skill=self.reading,
			question_type=self.mcq,
			topic=self.topic,
			difficulty_tier=self.beginner_tier,
			title=f'Q{idx}',
			question_text=f'Question {idx}',
			correct_answer='A',
			answer_matching_mode='normalized',
			points=1,
			is_active=True,
		)
		QuestionOption.objects.create(question=q, label='A', text='Correct', is_correct=True, order=1)
		QuestionOption.objects.create(question=q, label='B', text='Wrong', is_correct=False, order=2)
		return q

	def _create_text_question(self, qid, mode, correct, accepted=None):
		return Question.objects.create(
			question_id=qid,
			cefr_level=self.level_a1,
			sublevel=self.sub_a11,
			skill=self.reading,
			question_type=self.text_input,
			topic=self.topic,
			difficulty_tier=self.beginner_tier,
			title=qid,
			question_text='Fill answer',
			correct_answer=correct,
			accepted_answers=accepted or [],
			answer_matching_mode=mode,
			points=1,
			is_active=True,
		)

	def test_random_selection_unique_five_questions(self):
		for i in range(1, 11):
			self._create_mcq_question(i)

		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')
		engine.start_session()

		served_ids = []
		for _ in range(5):
			q = engine.get_next_question()
			self.assertIsNotNone(q)
			served_ids.append(q.id)
			engine.submit_answer(q, selected_option_label='A')

		self.assertEqual(len(served_ids), 5)
		self.assertEqual(len(set(served_ids)), 5)

	def test_retry_attempt_avoids_immediate_repetition_when_pool_allows(self):
		for i in range(1, 11):
			self._create_mcq_question(i)

		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')
		engine.start_session()

		first_attempt_ids = set()
		for _ in range(5):
			q = engine.get_next_question()
			first_attempt_ids.add(q.id)
			# First wrong -> same question retry
			retry_result = engine.submit_answer(q, selected_option_label='B')
			self.assertEqual(retry_result['action'], 'QUESTION_RETRY')
			q_retry = engine.get_next_question()
			self.assertEqual(q_retry.id, q.id)
			# Second wrong -> finalize and move on
			engine.submit_answer(q_retry, selected_option_label='B')

		second_attempt_ids = set()
		for _ in range(5):
			q = engine.get_next_question()
			second_attempt_ids.add(q.id)
			engine.submit_answer(q, selected_option_label='B')
			q_retry = engine.get_next_question()
			engine.submit_answer(q_retry, selected_option_label='B')

		self.assertTrue(first_attempt_ids.isdisjoint(second_attempt_ids))

	def test_two_attempt_rule_same_question_then_finalize(self):
		q = self._create_mcq_question(1)
		for i in range(2, 6):
			self._create_mcq_question(i)

		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')
		engine.start_session()

		first = engine.submit_answer(q, selected_option_label='B')
		self.assertEqual(first['action'], 'QUESTION_RETRY')
		self.assertEqual(first['question_attempt'], 1)
		self.assertEqual(first['total_questions'], 0)

		second = engine.submit_answer(q, selected_option_label='B')
		self.assertNotEqual(second['action'], 'QUESTION_RETRY')
		self.assertEqual(second['question_attempt'], 2)
		self.assertEqual(second['total_questions'], 1)

	def test_text_input_normalization_and_blank_handling(self):
		q = self._create_text_question('A1-T-001', mode='normalized', correct='hello')
		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')

		ok = engine._grade_text_input(q, '  HeLLo  ', 1.0)
		self.assertTrue(ok[0])

		blank = engine._grade_text_input(q, '   ', 1.0)
		self.assertFalse(blank[0])

	def test_text_input_multi_accepted_case_insensitive(self):
		q = self._create_text_question(
			'A1-T-002',
			mode='multi_accepted',
			correct='music and reading',
			accepted=['music and books', 'music and reading'],
		)
		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')

		ok = engine._grade_text_input(q, '  MUSIC AND BOOKS ', 1.0)
		self.assertTrue(ok[0])

	def test_pass_rule_80_unlocks_next_sublevel(self):
		for i in range(1, 6):
			self._create_mcq_question(i)

		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')
		engine.start_session()

		# 4/5 correct => 80%
		for idx in range(5):
			question = engine.get_next_question()
			if idx < 4:
				engine.submit_answer(question, selected_option_label='A')
			else:
				engine.submit_answer(question, selected_option_label='B')
				retry_q = engine.get_next_question()
				engine.submit_answer(retry_q, selected_option_label='B')

		final = engine.finish_session()
		self.candidate.refresh_from_db()

		self.assertGreaterEqual(final['percentage'], 80.0)
		self.assertTrue(final['level_passed'])
		self.assertEqual(self.candidate.current_sublevel.code, 'A1.2')

	def test_below_80_does_not_unlock_next_sublevel(self):
		for i in range(1, 6):
			self._create_mcq_question(i)

		engine = AdaptiveEngine(self.candidate, starting_level_code='A1', skill_code='reading')
		engine.start_session()

		# 3/5 correct => 60%
		for idx in range(5):
			question = engine.get_next_question()
			if idx < 3:
				engine.submit_answer(question, selected_option_label='A')
			else:
				engine.submit_answer(question, selected_option_label='B')
				retry_q = engine.get_next_question()
				engine.submit_answer(retry_q, selected_option_label='B')

		final = engine.finish_session()
		self.candidate.refresh_from_db()

		self.assertLess(final['percentage'], 80.0)
		self.assertFalse(final['level_passed'])
		self.assertEqual(self.candidate.current_sublevel.code, 'A1.1')
