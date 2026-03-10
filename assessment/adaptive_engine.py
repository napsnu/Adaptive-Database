"""
Adaptive Assessment Engine for CEFR English Learning Platform.

Supports all 4 skills (Reading, Writing, Speaking, Listening) and all
question types (MCQ, fill-in, matching, ordering, essay, etc.).

Algorithm:
 - Start at chosen CEFR level, optionally focused on one skill
 - Serve questions from the current level in batches of 3
 - Auto-grade objective questions (MCQ, true/false, fill-in, matching, ordering)
 - After each batch, evaluate accuracy:
     >= 2/3 correct  ->  Level UP
     == 1/3 correct  ->  STAY
     == 0/3 correct  ->  Level DOWN
 - Converge when STAY occurs twice consecutively at the same level
 - Maximum 15 questions per session
 - Determine final assessed CEFR level
"""

import random
from django.db import models
from django.utils import timezone
from assessment.models import (
    CEFRLevel, Skill, Question, QuestionOption, MatchingPair, OrderingItem,
    Candidate, AssessmentSession, Response, SkillScore,
)


class AdaptiveEngine:
    """
    Multi-skill adaptive engine for CEFR English Learning.

    Usage:
        engine = AdaptiveEngine(candidate, starting_level_code='A1', skill_code='reading')
        engine.start_session()

        while not engine.is_finished():
            question = engine.get_next_question()
            if question is None:
                break
            result = engine.submit_answer(question, selected_option_label='B')
            # result tells you if correct, score, level action, etc.

        final = engine.finish_session()
    """

    BATCH_SIZE = 3
    UP_THRESHOLD = 2       # >= 2 correct in batch -> level up
    DOWN_THRESHOLD = 0     # == 0 correct in batch -> level down
    MAX_QUESTIONS = 15
    STAY_TO_CONVERGE = 2   # 2 consecutive STAY -> converge

    def __init__(self, candidate, starting_level_code='A1', skill_code=None,
                 session_type='practice'):
        self.candidate = candidate
        self.starting_level = CEFRLevel.objects.get(code=starting_level_code)
        self.current_level = self.starting_level
        self.skill = Skill.objects.get(code=skill_code) if skill_code else None
        self.session_type = session_type

        self.session = None
        self.total_questions = 0
        self.total_correct = 0
        self.total_score = 0.0
        self.total_max_score = 0.0
        self.used_question_ids = set()

        # Batch tracking
        self._batch_correct = 0
        self._batch_count = 0

        # Convergence tracking
        self._consecutive_stays = 0
        self._finished = False
        self._history = []

    def start_session(self):
        """Create a new AssessmentSession."""
        self.session = AssessmentSession.objects.create(
            candidate=self.candidate,
            session_type=self.session_type,
            skill_focus=self.skill,
            starting_level=self.starting_level,
            current_level=self.current_level,
        )
        return self.session

    def is_finished(self):
        if self._finished:
            return True
        if self.total_questions >= self.MAX_QUESTIONS:
            return True
        return False

    def get_next_question(self):
        """Select the next question from the current level (optionally filtered by skill)."""
        if self.is_finished():
            return None

        qs = Question.objects.filter(
            cefr_level=self.current_level,
            is_active=True,
        ).exclude(id__in=self.used_question_ids)

        if self.skill:
            qs = qs.filter(skill=self.skill)

        # Prefer auto-gradable questions for adaptive accuracy,
        # but also include speaking questions (graded via speech transcription)
        speaking_skill = Skill.objects.filter(code='speaking').first()
        gradable_qs = list(qs.filter(
            models.Q(question_type__is_auto_gradable=True) |
            models.Q(skill=speaking_skill)
        ))
        if gradable_qs:
            return random.choice(gradable_qs)

        all_qs = list(qs)
        if all_qs:
            return random.choice(all_qs)

        self._finished = True
        return None

    def submit_answer(self, question, selected_option_label=None,
                      response_text='', response_data=None,
                      audio_file_path='', manual_score=None):
        """
        Submit and grade an answer.

        For auto-gradable questions:
            - MCQ / true_false: pass selected_option_label (e.g. 'A', 'B')
            - text_input: pass response_text
            - matching: pass response_data = {'pairs': {'1': '3', '2': '1', ...}}
            - ordering: pass response_data = {'order': [3, 1, 2, 4]}

        For subjective questions (essay, audio):
            - pass manual_score (0.0 - 1.0 fraction of points)
        """
        is_correct = None
        score = 0.0
        max_score = float(question.points)
        feedback = ''

        selected_option = None

        if question.question_type.is_auto_gradable:
            is_correct, score, feedback, selected_option = self._auto_grade(
                question, selected_option_label, response_text, response_data
            )
        elif question.skill.code == 'speaking' and response_text.strip():
            # Speaking with transcribed speech (from Web Speech API)
            is_correct, score, feedback, selected_option = self._grade_speaking(
                question, response_text, max_score
            )
        else:
            # Subjective: use manual_score if provided, else treat as 0
            if manual_score is not None:
                score = max_score * max(0.0, min(1.0, manual_score))
                is_correct = score >= max_score * 0.6
                feedback = 'Manually scored'
            else:
                score = 0.0
                is_correct = False
                feedback = 'Awaiting scoring'

        # Save response
        response = Response.objects.create(
            session=self.session,
            question=question,
            candidate=self.candidate,
            selected_option=selected_option,
            response_text=response_text,
            response_data=response_data,
            audio_file_path=audio_file_path,
            is_correct=is_correct,
            score=score,
            max_score=max_score,
            feedback=feedback,
        )

        self.used_question_ids.add(question.id)
        self.total_questions += 1
        self.total_score += score
        self.total_max_score += max_score
        if is_correct:
            self.total_correct += 1

        # Batch tracking
        self._batch_count += 1
        if is_correct:
            self._batch_correct += 1

        # Evaluate batch
        action = 'CONTINUE'
        old_level = self.current_level.code

        if self._batch_count >= self.BATCH_SIZE:
            action = self._evaluate_batch()
            self._batch_count = 0
            self._batch_correct = 0

        result = {
            'question_id': question.question_id,
            'is_correct': is_correct,
            'score': score,
            'max_score': max_score,
            'feedback': feedback,
            'previous_level': old_level,
            'current_level': self.current_level.code,
            'action': action,
            'batch_progress': f"{self._batch_count}/{self.BATCH_SIZE}",
            'total_questions': self.total_questions,
            'total_correct': self.total_correct,
        }
        self._history.append(result)

        # Update session
        self.session.current_level = self.current_level
        self.session.total_questions = self.total_questions
        self.session.correct_answers = self.total_correct
        self.session.total_score = self.total_score
        self.session.max_possible_score = self.total_max_score
        self.session.save(update_fields=[
            'current_level', 'total_questions', 'correct_answers',
            'total_score', 'max_possible_score'
        ])

        return result

    def _evaluate_batch(self):
        """Evaluate a completed batch and decide level movement."""
        correct = self._batch_correct

        if correct >= self.UP_THRESHOLD:
            next_up = self._get_next_level_up()
            if next_up:
                self.current_level = next_up
                self._consecutive_stays = 0
                return 'LEVEL UP'
            else:
                # Already at C2, converge
                self._finished = True
                return 'CONVERGE (MAX)'

        elif correct <= self.DOWN_THRESHOLD:
            next_down = self._get_next_level_down()
            if next_down:
                self.current_level = next_down
                self._consecutive_stays = 0
                return 'LEVEL DOWN'
            else:
                # Already at A1, converge
                self._finished = True
                return 'CONVERGE (MIN)'

        else:
            # STAY
            self._consecutive_stays += 1
            if self._consecutive_stays >= self.STAY_TO_CONVERGE:
                self._finished = True
                return 'CONVERGE'
            return 'STAY'

    def finish_session(self):
        """Finalize the session and compute skill scores."""
        self.session.final_level = self.current_level
        self.session.ended_at = timezone.now()
        self.session.is_completed = True
        self.session.save()

        # Update candidate's level
        self.candidate.current_cefr_level = self.current_level
        self.candidate.save(update_fields=['current_cefr_level'])

        # Compute per-skill scores
        self._compute_skill_scores()

        pct = 0.0
        if self.total_max_score > 0:
            pct = round((self.total_score / self.total_max_score) * 100, 1)

        return {
            'session_id': str(self.session.id),
            'candidate': self.candidate.name,
            'session_type': self.session_type,
            'skill_focus': self.skill.name if self.skill else 'All Skills',
            'starting_level': self.starting_level.code,
            'final_level': self.current_level.code,
            'total_questions': self.total_questions,
            'total_correct': self.total_correct,
            'total_score': self.total_score,
            'max_possible_score': self.total_max_score,
            'percentage': pct,
            'history': self._history,
        }

    def _compute_skill_scores(self):
        """Compute and save per-skill score breakdowns."""
        responses = Response.objects.filter(session=self.session).select_related('question__skill')
        skill_data = {}
        for resp in responses:
            sk = resp.question.skill
            if sk.id not in skill_data:
                skill_data[sk.id] = {
                    'skill': sk, 'total': 0, 'correct': 0, 'score': 0.0, 'max': 0.0
                }
            d = skill_data[sk.id]
            d['total'] += 1
            if resp.is_correct:
                d['correct'] += 1
            d['score'] += resp.score
            d['max'] += resp.max_score

        for d in skill_data.values():
            pct = round((d['score'] / d['max']) * 100, 1) if d['max'] > 0 else 0
            achieved = self._percentage_to_level(pct)
            SkillScore.objects.update_or_create(
                session=self.session,
                skill=d['skill'],
                defaults={
                    'total_questions': d['total'],
                    'correct_answers': d['correct'],
                    'total_score': d['score'],
                    'max_possible_score': d['max'],
                    'percentage': pct,
                    'cefr_level_achieved': achieved,
                }
            )

    def _auto_grade(self, question, selected_label, response_text, response_data):
        """Auto-grade objective questions. Returns (is_correct, score, feedback, selected_option)."""
        fmt = question.question_type.response_format
        max_score = float(question.points)
        selected_option = None

        if fmt in ('single_choice', 'true_false'):
            return self._grade_choice(question, selected_label, max_score)

        elif fmt == 'text_input':
            return self._grade_text_input(question, response_text, max_score)

        elif fmt == 'matching':
            return self._grade_matching(question, response_data, max_score)

        elif fmt == 'ordering':
            return self._grade_ordering(question, response_data, max_score)

        return False, 0.0, 'Unknown format', None

    def _grade_choice(self, question, selected_label, max_score):
        """Grade a single-choice or true/false question."""
        if not selected_label:
            return False, 0.0, 'No answer selected', None

        try:
            option = QuestionOption.objects.get(
                question=question, label__iexact=selected_label.strip()
            )
        except QuestionOption.DoesNotExist:
            return False, 0.0, f'Invalid option: {selected_label}', None

        if option.is_correct:
            return True, max_score, 'Correct!', option

        correct_opt = QuestionOption.objects.filter(question=question, is_correct=True).first()
        fb = f'Incorrect. The correct answer is {correct_opt.label}. {correct_opt.text}' if correct_opt else 'Incorrect.'
        if question.explanation:
            fb += f' | {question.explanation}'
        return False, 0.0, fb, option

    def _grade_text_input(self, question, response_text, max_score):
        """Grade a fill-in-the-gap or short answer question."""
        if not response_text.strip():
            return False, 0.0, 'No answer provided', None

        correct = question.correct_answer.strip().lower()
        # Support multiple correct answers separated by |
        correct_options = [c.strip() for c in correct.split('|')]
        answer = response_text.strip().lower()

        if answer in correct_options:
            return True, max_score, 'Correct!', None

        fb = f'Incorrect. The correct answer is: {question.correct_answer}'
        if question.explanation:
            fb += f' | {question.explanation}'
        return False, 0.0, fb, None

    def _grade_matching(self, question, response_data, max_score):
        """Grade a matching question. response_data = {'pairs': {'1':'2', '2':'1', ...}}"""
        pairs = list(MatchingPair.objects.filter(question=question).order_by('order'))
        if not pairs or not response_data or 'pairs' not in response_data:
            return False, 0.0, 'No matching data provided', None

        user_pairs = response_data['pairs']
        correct_count = 0
        for i, pair in enumerate(pairs):
            user_match = user_pairs.get(str(i + 1))
            if str(user_match) == str(i + 1):
                correct_count += 1

        total = len(pairs)
        if correct_count == total:
            return True, max_score, f'All {total} pairs matched correctly!', None

        score = max_score * (correct_count / total)
        return False, round(score, 2), f'{correct_count}/{total} pairs correct', None

    def _grade_ordering(self, question, response_data, max_score):
        """Grade an ordering question. response_data = {'order': [2, 1, 3, 4]}"""
        items = list(OrderingItem.objects.filter(question=question).order_by('correct_position'))
        if not items or not response_data or 'order' not in response_data:
            return False, 0.0, 'No ordering data provided', None

        user_order = response_data['order']
        correct_count = 0
        for i, item in enumerate(items):
            if i < len(user_order) and user_order[i] == item.correct_position:
                correct_count += 1

        total = len(items)
        if correct_count == total:
            return True, max_score, f'All {total} items in correct order!', None

        score = max_score * (correct_count / total)
        return False, round(score, 2), f'{correct_count}/{total} items correct', None

    def _grade_speaking(self, question, response_text, max_score):
        """
        Grade a speaking question using the transcribed speech text.

        - read_aloud: Compare transcription to the expected passage (text similarity)
        - describe_picture / opinion: Check minimum word count and give a participation score
        """
        qtype_code = question.question_type.code
        spoken_text = response_text.strip()

        if not spoken_text:
            return False, 0.0, 'No speech detected. Please try speaking again.', None

        if qtype_code == 'read_aloud':
            # Compare spoken text to the expected passage text
            expected = question.content_text or question.question_text or ''
            similarity = self._text_similarity(spoken_text, expected)

            if similarity >= 0.8:
                return True, max_score, f'Excellent reading! ({similarity:.0%} accuracy)', None
            elif similarity >= 0.5:
                score = max_score * similarity
                return True, round(score, 2), f'Good attempt ({similarity:.0%} accuracy). Keep practicing pronunciation.', None
            else:
                score = max_score * similarity
                return False, round(score, 2), f'Try to read the passage more carefully ({similarity:.0%} accuracy).', None

        else:
            # describe_picture, opinion_essay — grade by word count & effort
            word_count = len(spoken_text.split())

            # Minimum word thresholds per CEFR level
            level_order = question.cefr_level.order  # 1=A1, 6=C2
            min_words = 5 + (level_order * 5)  # A1=10, A2=15, B1=20, B2=25, C1=30, C2=35

            if word_count >= min_words:
                score = max_score * 0.8  # Good effort = 80%
                return True, round(score, 2), f'Good response! ({word_count} words spoken)', None
            elif word_count >= min_words * 0.5:
                score = max_score * 0.5
                return False, round(score, 2), f'Try to speak more ({word_count}/{min_words} words minimum)', None
            else:
                score = max_score * 0.2
                return False, round(score, 2), f'Response too short ({word_count} words). Try to elaborate more.', None

    @staticmethod
    def _text_similarity(text1, text2):
        """Simple word-overlap similarity score (0.0 to 1.0)."""
        import re
        words1 = set(re.findall(r'[a-z]+', text1.lower()))
        words2 = set(re.findall(r'[a-z]+', text2.lower()))
        if not words2:
            return 0.0
        overlap = words1 & words2
        return len(overlap) / len(words2)

    def _get_next_level_up(self):
        try:
            return CEFRLevel.objects.get(order=self.current_level.order + 1)
        except CEFRLevel.DoesNotExist:
            return None

    def _get_next_level_down(self):
        try:
            return CEFRLevel.objects.get(order=self.current_level.order - 1)
        except CEFRLevel.DoesNotExist:
            return None

    def _percentage_to_level(self, pct):
        """Map a percentage score to a CEFR level."""
        if pct >= 85:
            code = 'C2'
        elif pct >= 70:
            code = 'C1'
        elif pct >= 55:
            code = 'B2'
        elif pct >= 40:
            code = 'B1'
        elif pct >= 25:
            code = 'A2'
        else:
            code = 'A1'
        try:
            return CEFRLevel.objects.get(code=code)
        except CEFRLevel.DoesNotExist:
            return self.current_level
