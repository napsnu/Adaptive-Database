"""
Hierarchical Assessment Engine for CEFR English Learning Platform.

Supports all 4 skills (Reading, Writing, Speaking, Listening) with a
strict hierarchical progression:

Algorithm:
 - Candidate selects a CEFR level (A1–C2)
 - Skills are tested in fixed order: Reading → Writing → Speaking → Listening
 - Each skill round: 3 questions from the current skill
 - Pass threshold: >= 2/3 correct to pass the skill
 - PASS  → skill marked complete, move to next skill
 - FAIL  → must retry the same skill (different questions if available)
 - Overall score >= 80% → level passed, next level unlocked
 - Overall score < 80% → level not passed, candidate stays at current level
 - Maximum 2 retries per skill (3 attempts total), then forced move to next skill
"""

import random
import math
from django.db import models
from django.utils import timezone
from assessment.models import (
    CEFRLevel, CEFRSubLevel, Skill, Question, QuestionOption, MatchingPair, OrderingItem,
    Candidate, AssessmentSession, Response, SkillScore, AnswerSample,
    UserAttempt, UserProgress,
)
from assessment.ai_services import grade_with_gemini


# Skill order for hierarchical progression
SKILL_ORDER = ['reading', 'writing', 'listening', 'speaking']


class AdaptiveEngine:
    """
    Hierarchical adaptive engine for CEFR English Learning.

    Flow: Level → Reading (3Q) → Writing (3Q) → Speaking (3Q) → Listening (3Q)
    Must pass each skill (2/3 correct) before moving to the next.

    Usage:
        engine = AdaptiveEngine(candidate, starting_level_code='A1')
        engine.start_session()

        while not engine.is_finished():
            question = engine.get_next_question()
            if question is None:
                break
            result = engine.submit_answer(question, selected_option_label='B')

        final = engine.finish_session()
    """

    QUESTIONS_PER_SKILL = 3
    SUBLEVEL_QUESTIONS_PER_SKILL = 1
    PASS_THRESHOLD = 2      # >= 2 correct out of 3 to pass a skill
    MAX_RETRIES = 2         # max retries per skill (3 attempts total)

    def __init__(self, candidate, starting_level_code='A1', skill_code=None,
                 session_type='practice', starting_sublevel_code=None):
        self.candidate = candidate
        self.starting_level = CEFRLevel.objects.get(code=starting_level_code)
        self.current_level = self.starting_level
        self.current_sublevel = self._resolve_starting_sublevel(starting_sublevel_code)
        self.session_type = session_type
        self.questions_per_skill = (
            self.SUBLEVEL_QUESTIONS_PER_SKILL if self.current_sublevel else self.QUESTIONS_PER_SKILL
        )

        # If a specific skill is given, test only that skill
        if skill_code:
            self._skill_order = [skill_code]
        else:
            self._skill_order = list(SKILL_ORDER)

        self.session = None
        self.total_questions = 0
        self.total_correct = 0
        self.total_score = 0.0
        self.total_max_score = 0.0
        self.used_question_ids = set()

        # Hierarchical tracking
        self._current_skill_index = 0
        self._current_skill_correct = 0
        self._current_skill_count = 0
        self._current_skill_attempt = 1  # which attempt (1, 2, or 3)

        # Track passed/failed skills
        self._skill_results = {}  # {skill_code: {'passed': bool, 'attempts': int, 'scores': []}}
        for sk in self._skill_order:
            self._skill_results[sk] = {'passed': False, 'attempts': 0, 'scores': []}

        self._finished = False
        self._history = []

    @property
    def current_skill_code(self):
        if self._current_skill_index < len(self._skill_order):
            return self._skill_order[self._current_skill_index]
        return None

    @property
    def current_skill(self):
        code = self.current_skill_code
        if code:
            return Skill.objects.get(code=code)
        return None

    def _resolve_starting_sublevel(self, starting_sublevel_code):
        if starting_sublevel_code:
            return CEFRSubLevel.objects.get(code=starting_sublevel_code, cefr_level=self.starting_level)
        if self.candidate.current_sublevel and self.candidate.current_sublevel.cefr_level_id == self.starting_level.id:
            return self.candidate.current_sublevel
        return CEFRSubLevel.objects.filter(cefr_level=self.starting_level, is_active=True).order_by('unit_order').first()

    def start_session(self):
        """Create a new AssessmentSession."""
        skill_focus = None
        if len(self._skill_order) == 1:
            skill_focus = Skill.objects.get(code=self._skill_order[0])

        self.session = AssessmentSession.objects.create(
            candidate=self.candidate,
            session_type=self.session_type,
            skill_focus=skill_focus,
            starting_level=self.starting_level,
            starting_sublevel=self.current_sublevel,
            current_level=self.current_level,
            current_sublevel=self.current_sublevel,
        )
        return self.session

    def is_finished(self):
        if self._finished:
            return True
        if self._current_skill_index >= len(self._skill_order):
            return True
        return False

    def get_next_question(self):
        """Select the next question from the current skill at the current level."""
        if self.is_finished():
            return None

        skill_code = self.current_skill_code
        if not skill_code:
            self._finished = True
            return None

        skill = Skill.objects.get(code=skill_code)

        base_qs = Question.objects.filter(
            cefr_level=self.current_level,
            skill=skill,
            is_active=True,
        ).exclude(id__in=self.used_question_ids)

        qs = base_qs
        if self.current_sublevel:
            qs = qs.filter(sublevel=self.current_sublevel)
            if not qs.exists():
                # Backward compatibility for older banks that don't have sublevel assigned yet.
                qs = base_qs

        all_qs = list(qs)
        if all_qs:
            return random.choice(all_qs)

        # No more questions available for this skill — skip to next
        self._advance_skill(forced=True)
        return self.get_next_question() if not self.is_finished() else None

    def submit_answer(self, question, selected_option_label=None,
                      response_text='', response_data=None,
                      audio_file_path='', manual_score=None):
        """Submit and grade an answer."""
        is_correct = None
        score = 0.0
        max_score = float(question.points)
        feedback = ''
        selected_option = None

        if question.skill.code == 'writing' and response_text.strip():
            is_correct, score, feedback, selected_option = self._grade_writing_with_samples(
                question, response_text, max_score
            )
        elif question.question_type.is_auto_gradable:
            is_correct, score, feedback, selected_option = self._auto_grade(
                question, selected_option_label, response_text, response_data
            )
        elif question.skill.code in ('speaking', 'listening') and response_text.strip():
            is_correct, score, feedback, selected_option = self._grade_speaking(
                question, response_text, max_score
            )
        else:
            if manual_score is not None:
                score = max_score * max(0.0, min(1.0, manual_score))
                is_correct = score >= max_score * 0.6
                feedback = 'Manually scored'
            else:
                score = 0.0
                is_correct = False
                feedback = 'Awaiting scoring'

        # Save response
        Response.objects.create(
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

        UserAttempt.objects.create(
            candidate=self.candidate,
            session=self.session,
            question=question,
            skill=question.skill,
            cefr_level=question.cefr_level,
            sublevel=question.sublevel,
            submitted_answer=(response_text or selected_option_label or ''),
            is_correct=bool(is_correct),
            score=score,
            max_score=max_score,
            attempt_no=self._skill_results[self.current_skill_code]['attempts'] + 1,
        )

        progress_sublevel = question.sublevel or self.current_sublevel
        if progress_sublevel:
            progress_obj, _ = UserProgress.objects.get_or_create(
                candidate=self.candidate,
                cefr_level=question.cefr_level,
                sublevel=progress_sublevel,
                skill=question.skill,
                defaults={'is_unlocked': True},
            )
            progress_obj.questions_answered += 1
            if is_correct:
                progress_obj.correct_answers += 1
            progress_obj.attempts += 1
            progress_obj.mastery_score = round(
                (progress_obj.correct_answers / progress_obj.questions_answered) * 100,
                1,
            ) if progress_obj.questions_answered > 0 else 0
            progress_obj.is_completed = progress_obj.mastery_score >= 80.0
            progress_obj.last_attempt_at = timezone.now()
            progress_obj.save(update_fields=[
                'questions_answered', 'correct_answers', 'attempts',
                'mastery_score', 'is_completed', 'last_attempt_at',
            ])

        self.used_question_ids.add(question.id)
        self.total_questions += 1
        self.total_score += score
        self.total_max_score += max_score
        if is_correct:
            self.total_correct += 1

        # Skill-level tracking
        self._current_skill_count += 1
        if is_correct:
            self._current_skill_correct += 1

        # Evaluate after configured number of questions per skill
        action = 'CONTINUE'
        skill_status = None

        if self._current_skill_count >= self.questions_per_skill:
            action, skill_status = self._evaluate_skill()

        result = {
            'question_id': question.question_id,
            'is_correct': is_correct,
            'score': score,
            'max_score': max_score,
            'feedback': feedback,
            'current_level': self.current_level.code,
            'current_skill': self.current_skill_code,
            'action': action,
            'skill_status': skill_status,
            'skill_progress': f"{self._current_skill_count}/{self.questions_per_skill}",
            'skills_passed': [k for k, v in self._skill_results.items() if v['passed']],
            'skills_remaining': [k for k in self._skill_order[self._current_skill_index:]],
            'total_questions': self.total_questions,
            'total_correct': self.total_correct,
            'current_sublevel': self.current_sublevel.code if self.current_sublevel else None,
        }
        self._history.append(result)

        # Update session
        self.session.current_level = self.current_level
        self.session.current_sublevel = self.current_sublevel
        self.session.total_questions = self.total_questions
        self.session.correct_answers = self.total_correct
        self.session.total_score = self.total_score
        self.session.max_possible_score = self.total_max_score
        self.session.save(update_fields=[
            'current_level', 'current_sublevel', 'total_questions', 'correct_answers',
            'total_score', 'max_possible_score'
        ])

        return result

    def _grade_writing_with_samples(self, question, response_text, max_score):
        """Grade writing using multiple acceptable samples via similarity + keyword overlap."""
        answer = response_text.strip()
        if not answer:
            return False, 0.0, 'No answer provided', None

        samples = list(question.answer_samples.all())
        # Backward compatible fallback to sample_answer if explicit samples are not seeded yet
        if not samples and question.sample_answer:
            pseudo_samples = [s.strip() for s in question.sample_answer.split('|') if s.strip()]
            for idx, text in enumerate(pseudo_samples):
                samples.append(AnswerSample(question=question, text=text, keywords=[] , order=idx))

        if not samples:
            # Last-resort fallback to text-input rule
            return self._grade_text_input(question, response_text, max_score)

        best_score = 0.0
        for sample in samples:
            similarity = self._sequence_similarity(answer, sample.text)
            keyword_score = self._keyword_overlap(answer, sample.keywords)
            composite = (similarity * 0.75) + (keyword_score * 0.25)
            if composite > best_score:
                best_score = composite

        if best_score >= 0.7:
            return True, max_score, f'Good writing response ({best_score:.0%} match).', None
        if best_score >= 0.5:
            partial = round(max_score * best_score, 2)
            return False, partial, f'Partially correct writing response ({best_score:.0%} match).', None
        return False, 0.0, f'Response does not match expected writing patterns ({best_score:.0%} match).', None

    @staticmethod
    def _sequence_similarity(text1, text2):
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()

    @staticmethod
    def _keyword_overlap(answer, keywords):
        if not keywords:
            return 1.0
        answer_tokens = set(w.strip('.,!?;:()[]{}').lower() for w in answer.split() if w.strip())
        kw_tokens = set(str(k).lower() for k in keywords if str(k).strip())
        if not kw_tokens:
            return 1.0
        return len(answer_tokens & kw_tokens) / len(kw_tokens)

    def _evaluate_skill(self):
        """Evaluate skill round and decide: pass → next skill, fail → retry."""
        correct = self._current_skill_correct
        skill_code = self.current_skill_code
        pass_threshold = max(1, math.ceil(self.questions_per_skill * 0.8))

        # Record this attempt
        self._skill_results[skill_code]['attempts'] += 1
        self._skill_results[skill_code]['scores'].append(
            f"{correct}/{self.questions_per_skill}"
        )

        if correct >= pass_threshold:
            # PASSED this skill
            self._skill_results[skill_code]['passed'] = True
            self._advance_skill(forced=False)
            return 'SKILL_PASSED', {
                'skill': skill_code,
                'result': 'PASSED',
                'score': f"{correct}/{self.questions_per_skill}",
                'next_skill': self.current_skill_code,
                'message': f'Well done! You passed {skill_code.title()}.',
            }
        else:
            # FAILED this skill
            if self._current_skill_attempt >= self.MAX_RETRIES + 1:
                # Max retries reached — force move to next skill
                self._advance_skill(forced=True)
                return 'SKILL_FAILED_MAX_RETRIES', {
                    'skill': skill_code,
                    'result': 'FAILED',
                    'score': f"{correct}/{self.questions_per_skill}",
                    'next_skill': self.current_skill_code,
                    'message': f'You did not pass {skill_code.title()} after {self.MAX_RETRIES + 1} attempts. Moving on.',
                }
            else:
                # Retry the same skill
                self._current_skill_attempt += 1
                self._current_skill_correct = 0
                self._current_skill_count = 0
                return 'SKILL_FAILED_RETRY', {
                    'skill': skill_code,
                    'result': 'RETRY',
                    'score': f"{correct}/{self.questions_per_skill}",
                    'attempt': self._current_skill_attempt,
                    'max_attempts': self.MAX_RETRIES + 1,
                    'message': f'You need {pass_threshold}/{self.questions_per_skill} to pass. Try {skill_code.title()} again! (Attempt {self._current_skill_attempt}/{self.MAX_RETRIES + 1})',
                }

    def _advance_skill(self, forced=False):
        """Move to the next skill in the hierarchy."""
        self._current_skill_index += 1
        self._current_skill_correct = 0
        self._current_skill_count = 0
        self._current_skill_attempt = 1

        if self._current_skill_index >= len(self._skill_order):
            # All skills attempted — level assessment complete
            self._finished = True

    def get_progress(self):
        """Return detailed progress info for the frontend."""
        return {
            'current_level': self.current_level.code,
            'current_skill': self.current_skill_code,
            'current_skill_attempt': self._current_skill_attempt,
            'max_attempts': self.MAX_RETRIES + 1,
            'questions_in_skill': self._current_skill_count,
            'questions_per_skill': self.questions_per_skill,
            'skill_order': self._skill_order,
            'skills_passed': [k for k, v in self._skill_results.items() if v['passed']],
            'skills_failed': [k for k, v in self._skill_results.items()
                              if not v['passed'] and v['attempts'] > 0],
            'skill_results': {k: v for k, v in self._skill_results.items()},
            'total_questions': self.total_questions,
            'total_correct': self.total_correct,
            'current_sublevel': self.current_sublevel.code if self.current_sublevel else None,
        }

    LEVEL_PASS_PERCENTAGE = 80.0  # >= 80% overall score to unlock next level

    def finish_session(self):
        """Finalize the session and compute skill scores."""
        self.session.final_level = self.current_level
        self.session.final_sublevel = self.current_sublevel
        self.session.ended_at = timezone.now()
        self.session.is_completed = True
        self.session.save(update_fields=['final_level', 'final_sublevel', 'ended_at', 'is_completed'])

        # Compute per-skill scores
        self._compute_skill_scores()

        # Calculate overall percentage
        pct = 0.0
        if self.total_max_score > 0:
            pct = round((self.total_score / self.total_max_score) * 100, 1)

        # Level passes if overall score >= 80%
        level_passed = pct >= self.LEVEL_PASS_PERCENTAGE

        # Update candidate's sublevel/level if score >= 80%
        if level_passed:
            next_sublevel = self._get_next_sublevel_up()
            if next_sublevel:
                self.candidate.current_cefr_level = next_sublevel.cefr_level
                self.candidate.current_sublevel = next_sublevel
            else:
                next_level = self._get_next_level_up()
                if next_level:
                    self.candidate.current_cefr_level = next_level
                    self.candidate.current_sublevel = CEFRSubLevel.objects.filter(
                        cefr_level=next_level,
                        is_active=True,
                    ).order_by('unit_order').first()
                else:
                    self.candidate.current_cefr_level = self.current_level
                    self.candidate.current_sublevel = self.current_sublevel
        else:
            self.candidate.current_cefr_level = self.current_level
            self.candidate.current_sublevel = self.current_sublevel
        self.candidate.save(update_fields=['current_cefr_level', 'current_sublevel'])

        return {
            'session_id': str(self.session.id),
            'candidate': self.candidate.name,
            'session_type': self.session_type,
            'level': self.current_level.code,
            'sublevel': self.current_sublevel.code if self.current_sublevel else None,
            'level_passed': level_passed,
            'next_level': self.candidate.current_cefr_level.code if level_passed and self.candidate.current_cefr_level else None,
            'next_sublevel': self.candidate.current_sublevel.code if level_passed and self.candidate.current_sublevel else None,
            'total_questions': self.total_questions,
            'total_correct': self.total_correct,
            'total_score': self.total_score,
            'max_possible_score': self.total_max_score,
            'percentage': pct,
            'pass_threshold': self.LEVEL_PASS_PERCENTAGE,
            'skill_results': {k: {
                'passed': v['passed'],
                'attempts': v['attempts'],
                'scores': v['scores'],
            } for k, v in self._skill_results.items()},
            'history': self._history,
        }

    def _get_next_sublevel_up(self):
        if not self.current_sublevel:
            return None
        return CEFRSubLevel.objects.filter(
            cefr_level=self.current_level,
            is_active=True,
            unit_order__gt=self.current_sublevel.unit_order,
        ).order_by('unit_order').first()

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
        Grade a speaking question using AI (Gemini) with basic fallback.

        - Sends the transcribed speech to Gemini for CEFR-level grading
        - Falls back to text similarity / word count if Gemini unavailable
        """
        qtype_code = question.question_type.code
        spoken_text = response_text.strip()

        if not spoken_text:
            return False, 0.0, 'No speech detected. Please try speaking again.', None

        # Try Gemini AI grading first
        expected = question.content_text or question.question_text or ''
        gemini_result = grade_with_gemini(
            question_text=question.question_text,
            response_text=spoken_text,
            skill_code='speaking',
            question_type_code=qtype_code,
            cefr_level=question.cefr_level.code,
            max_score=max_score,
            expected_text=expected if qtype_code == 'read_aloud' else None,
        )

        if gemini_result is not None:
            is_correct, score, feedback = gemini_result
            return is_correct, score, feedback, None

        # Fallback: basic grading if Gemini is unavailable
        return self._basic_grade_speaking(question, spoken_text, max_score, qtype_code)

    def _basic_grade_speaking(self, question, spoken_text, max_score, qtype_code):
        """Fallback basic speaking grading without AI."""
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
