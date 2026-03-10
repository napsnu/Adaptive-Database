"""
JSON API views for the Adaptive CEFR English Learning Platform.

Endpoints:
  GET  /api/                           — Dashboard stats
  GET  /api/levels/                    — List CEFR levels
  GET  /api/skills/                    — List skills
  GET  /api/question-types/            — List question types
  GET  /api/topics/                    — List topics
  GET  /api/questions/                 — List questions (filterable)
  GET  /api/questions/<qid>/           — Single question detail
  POST /api/session/start/             — Start adaptive session
  GET  /api/session/<id>/next/         — Get next question
  POST /api/session/<id>/answer/       — Submit answer
  GET  /api/session/<id>/results/      — Get session results
"""

import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import (
    CEFRLevel, Skill, QuestionType, Topic,
    Question, QuestionOption, MatchingPair, OrderingItem,
    Candidate, AssessmentSession, Response, SkillScore,
)
from .adaptive_engine import AdaptiveEngine


def _json_error(msg, status=400):
    return JsonResponse({'error': msg}, status=status)


def _parse_json(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None


# ── Read-Only Endpoints ──────────────────────────────────────────────

class DashboardView(View):
    def get(self, request):
        return JsonResponse({
            'platform': 'Adaptive CEFR English Learning Platform',
            'stats': {
                'levels': CEFRLevel.objects.count(),
                'skills': Skill.objects.count(),
                'question_types': QuestionType.objects.count(),
                'topics': Topic.objects.count(),
                'questions': Question.objects.filter(is_active=True).count(),
                'candidates': Candidate.objects.count(),
                'sessions': AssessmentSession.objects.count(),
            },
            'endpoints': [
                'GET /api/levels/', 'GET /api/skills/',
                'GET /api/question-types/', 'GET /api/topics/',
                'GET /api/questions/?level=A1&skill=reading',
                'GET /api/questions/<question_id>/',
                'POST /api/session/start/',
                'GET /api/session/<id>/next/',
                'POST /api/session/<id>/answer/',
                'GET /api/session/<id>/results/',
            ],
        })


class LevelListView(View):
    def get(self, request):
        levels = list(CEFRLevel.objects.values('code', 'name', 'order', 'description', 'min_score', 'max_score'))
        return JsonResponse({'levels': levels})


class SkillListView(View):
    def get(self, request):
        skills = list(Skill.objects.values('code', 'name', 'description', 'order'))
        return JsonResponse({'skills': skills})


class QuestionTypeListView(View):
    def get(self, request):
        types = []
        for qt in QuestionType.objects.prefetch_related('skills').all():
            types.append({
                'code': qt.code, 'name': qt.name,
                'response_format': qt.response_format,
                'is_auto_gradable': qt.is_auto_gradable,
                'skills': list(qt.skills.values_list('code', flat=True)),
            })
        return JsonResponse({'question_types': types})


class TopicListView(View):
    def get(self, request):
        topics = []
        for t in Topic.objects.prefetch_related('cefr_levels').all():
            topics.append({
                'code': t.code, 'name': t.name, 'description': t.description,
                'cefr_levels': list(t.cefr_levels.values_list('code', flat=True)),
            })
        return JsonResponse({'topics': topics})


class QuestionListView(View):
    def get(self, request):
        qs = Question.objects.filter(is_active=True).select_related(
            'cefr_level', 'skill', 'question_type', 'topic'
        )
        level = request.GET.get('level')
        skill = request.GET.get('skill')
        qtype = request.GET.get('type')
        topic = request.GET.get('topic')
        if level:
            qs = qs.filter(cefr_level__code=level)
        if skill:
            qs = qs.filter(skill__code=skill)
        if qtype:
            qs = qs.filter(question_type__code=qtype)
        if topic:
            qs = qs.filter(topic__code=topic)

        questions = []
        for q in qs[:100]:
            questions.append({
                'question_id': q.question_id,
                'title': q.title,
                'level': q.cefr_level.code,
                'skill': q.skill.code,
                'question_type': q.question_type.code,
                'topic': q.topic.code,
                'difficulty': q.difficulty,
                'points': q.points,
            })
        return JsonResponse({'questions': questions, 'count': len(questions)})


class QuestionDetailView(View):
    def get(self, request, question_id):
        try:
            q = Question.objects.select_related(
                'cefr_level', 'skill', 'question_type', 'topic'
            ).get(question_id=question_id)
        except Question.DoesNotExist:
            return _json_error('Question not found', 404)

        data = {
            'question_id': q.question_id, 'title': q.title,
            'level': q.cefr_level.code, 'skill': q.skill.code,
            'question_type': q.question_type.code, 'topic': q.topic.code,
            'instruction': q.instruction_text, 'content': q.content_text,
            'question': q.question_text,
            'media_url': q.media_url, 'media_type': q.media_type,
            'difficulty': q.difficulty, 'points': q.points,
            'time_limit': q.time_limit_seconds,
            'response_format': q.question_type.response_format,
        }

        fmt = q.question_type.response_format
        if fmt in ('single_choice', 'true_false'):
            data['options'] = list(q.options.values('label', 'text', 'media_url', 'order'))
        elif fmt == 'matching':
            data['pairs'] = list(q.matching_pairs.values('left_text', 'right_text', 'order'))
        elif fmt == 'ordering':
            items = list(q.ordering_items.values('text', 'correct_position'))
            import random
            random.shuffle(items)
            data['items'] = items

        return JsonResponse(data)


# ── Session Management ───────────────────────────────────────────────

_active_engines = {}


@method_decorator(csrf_exempt, name='dispatch')
class StartSessionView(View):
    def post(self, request):
        data = _parse_json(request)
        if not data:
            return _json_error('Invalid JSON body')

        email = data.get('email', '')
        if not email:
            return _json_error('email is required')

        name = data.get('name', 'Learner')
        level = data.get('starting_level', 'A1')
        skill_code = data.get('skill')
        session_type = data.get('session_type', 'practice')

        candidate, _ = Candidate.objects.get_or_create(
            email=email, defaults={'name': name}
        )

        try:
            engine = AdaptiveEngine(
                candidate, starting_level_code=level,
                skill_code=skill_code, session_type=session_type
            )
        except Exception as e:
            return _json_error(str(e))

        session = engine.start_session()
        _active_engines[str(session.id)] = engine

        progress = engine.get_progress()
        return JsonResponse({
            'session_id': str(session.id),
            'candidate': candidate.name,
            'starting_level': level,
            'skill': skill_code or 'all',
            'session_type': session_type,
            'progress': progress,
        })


class NextQuestionView(View):
    def get(self, request, session_id):
        engine = _active_engines.get(session_id)
        if not engine:
            return _json_error('Session not found or expired', 404)

        if engine.is_finished():
            progress = engine.get_progress()
            return JsonResponse({
                'finished': True,
                'message': 'Session complete',
                'progress': progress,
            })

        question = engine.get_next_question()
        if not question:
            progress = engine.get_progress()
            return JsonResponse({
                'finished': True,
                'message': 'No more questions available',
                'progress': progress,
            })

        progress = engine.get_progress()
        data = {
            'finished': False,
            'question_id': question.question_id,
            'title': question.title,
            'level': question.cefr_level.code,
            'skill': question.skill.code,
            'question_type': question.question_type.code,
            'instruction': question.instruction_text or question.question_type.instruction_template,
            'content': question.content_text,
            'question': question.question_text,
            'media_url': question.media_url,
            'media_type': question.media_type,
            'points': question.points,
            'time_limit': question.time_limit_seconds,
            'response_format': question.question_type.response_format,
            'progress': progress,
        }

        fmt = question.question_type.response_format
        if fmt in ('single_choice', 'true_false'):
            data['options'] = list(question.options.values('label', 'text', 'order'))
        elif fmt == 'matching':
            pairs = list(question.matching_pairs.values('left_text', 'right_text', 'order'))
            data['pairs'] = pairs
        elif fmt == 'ordering':
            items = list(question.ordering_items.values('text', 'correct_position'))
            import random
            random.shuffle(items)
            data['items'] = items

        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class SubmitAnswerView(View):
    def post(self, request, session_id):
        engine = _active_engines.get(session_id)
        if not engine:
            return _json_error('Session not found or expired', 404)

        data = _parse_json(request)
        if not data:
            return _json_error('Invalid JSON body')

        qid = data.get('question_id')
        if not qid:
            return _json_error('question_id is required')

        try:
            question = Question.objects.get(question_id=qid)
        except Question.DoesNotExist:
            return _json_error('Question not found', 404)

        result = engine.submit_answer(
            question,
            selected_option_label=data.get('selected_option'),
            response_text=data.get('response_text', ''),
            response_data=data.get('response_data'),
            manual_score=data.get('manual_score'),
        )

        return JsonResponse({'result': result})


class SessionResultsView(View):
    def get(self, request, session_id):
        engine = _active_engines.get(session_id)

        try:
            session = AssessmentSession.objects.get(id=session_id)
        except AssessmentSession.DoesNotExist:
            return _json_error('Session not found', 404)

        if engine and not session.is_completed:
            final = engine.finish_session()
            _active_engines.pop(session_id, None)
            return JsonResponse({'results': final})

        responses = Response.objects.filter(session=session).select_related('question')
        skill_scores = SkillScore.objects.filter(session=session).select_related('skill', 'cefr_level_achieved')

        return JsonResponse({
            'results': {
                'session_id': str(session.id),
                'candidate': session.candidate.name,
                'session_type': session.session_type,
                'starting_level': session.starting_level.code if session.starting_level else None,
                'final_level': session.final_level.code if session.final_level else None,
                'total_questions': session.total_questions,
                'correct_answers': session.correct_answers,
                'percentage': session.percentage,
                'is_completed': session.is_completed,
                'skill_scores': [{
                    'skill': ss.skill.name,
                    'questions': ss.total_questions,
                    'correct': ss.correct_answers,
                    'percentage': ss.percentage,
                    'level_achieved': ss.cefr_level_achieved.code if ss.cefr_level_achieved else None,
                } for ss in skill_scores],
                'responses': [{
                    'question_id': r.question.question_id,
                    'is_correct': r.is_correct,
                    'score': r.score,
                    'feedback': r.feedback,
                } for r in responses],
            }
        })
