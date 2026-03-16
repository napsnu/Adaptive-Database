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
  GET  /api/session/resume/?email=     — Check for incomplete session
  GET  /api/admin/analytics/           — Admin analytics dashboard
  POST /api/tts/                       — Generate TTS audio from text
"""

import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import (
    CEFRLevel, CEFRSubLevel, Skill, QuestionType, Topic,
    Question, QuestionOption, MatchingPair, OrderingItem,
    Candidate, AssessmentSession, Response, SkillScore, AnswerSample,
)
from .adaptive_engine import AdaptiveEngine
from .ai_services import generate_tts_audio


def _json_error(msg, status=400):
    return JsonResponse({'error': msg}, status=status)


def _parse_json(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None


def _normalize_response_format(fmt):
    """Map specialized formats to broadly supported frontend input types."""
    mapping = {
        'sentence_build': 'text_input',
        'picture_prompt': 'long_text',
    }
    return mapping.get(fmt, fmt)


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
                'GET /api/sublevels/?level=A1',
                'GET /api/question-types/', 'GET /api/topics/',
                'GET /api/questions/?level=A1&sublevel=A1.1&skill=reading',
                'GET /api/questions/<question_id>/',
                'POST /api/session/start/',
                'GET /api/session/<id>/next/',
                'POST /api/session/<id>/answer/',
                'GET /api/session/<id>/results/',
                'GET /api/session/resume/?email=user@example.com',
                'GET /api/admin/analytics/',
                'GET /api/admin/analytics/?email=user@example.com',
                'POST /api/tts/',
            ],
        })


class LevelListView(View):
    def get(self, request):
        levels = list(CEFRLevel.objects.values('code', 'name', 'order', 'description', 'min_score', 'max_score'))
        return JsonResponse({'levels': levels})


class SubLevelListView(View):
    def get(self, request):
        level = request.GET.get('level')
        qs = CEFRSubLevel.objects.select_related('cefr_level').filter(is_active=True)
        if level:
            qs = qs.filter(cefr_level__code=level)
        sublevels = list(qs.values(
            'code', 'title', 'unit_order',
            'cefr_level__code', 'cefr_level__name',
        ))
        return JsonResponse({'sublevels': sublevels, 'count': len(sublevels)})


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
            'cefr_level', 'sublevel', 'skill', 'question_type', 'topic'
        )
        level = request.GET.get('level')
        sublevel = request.GET.get('sublevel')
        skill = request.GET.get('skill')
        qtype = request.GET.get('type')
        topic = request.GET.get('topic')
        if level:
            qs = qs.filter(cefr_level__code=level)
        if sublevel:
            qs = qs.filter(sublevel__code=sublevel)
        if skill:
            qs = qs.filter(skill__code=skill)
        if qtype:
            qs = qs.filter(question_type__code=qtype)
        if topic:
            qs = qs.filter(topic__code=topic)

        tier = request.GET.get('tier')
        if tier:
            qs = qs.filter(difficulty_tier__code=tier)

        try:
            limit = int(request.GET.get('limit', 100))
        except ValueError:
            limit = 100
        try:
            offset = int(request.GET.get('offset', 0))
        except ValueError:
            offset = 0

        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        total_count = qs.count()

        questions = []
        for q in qs[offset:offset + limit]:
            questions.append({
                'question_id': q.question_id,
                'title': q.title,
                'level': q.cefr_level.code,
                'sublevel': q.sublevel.code if q.sublevel else None,
                'skill': q.skill.code,
                'question_type': q.question_type.code,
                'topic': q.topic.code,
                'difficulty': q.difficulty,
                'points': q.points,
            })
        return JsonResponse({
            'questions': questions,
            'count': len(questions),
            'total_count': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': offset + len(questions) < total_count,
        })


class QuestionDetailView(View):
    def get(self, request, question_id):
        try:
            q = Question.objects.select_related(
                'cefr_level', 'sublevel', 'skill', 'question_type', 'topic'
            ).get(question_id=question_id)
        except Question.DoesNotExist:
            return _json_error('Question not found', 404)

        data = {
            'question_id': q.question_id, 'title': q.title,
            'level': q.cefr_level.code, 'skill': q.skill.code,
            'sublevel': q.sublevel.code if q.sublevel else None,
            'question_type': q.question_type.code, 'topic': q.topic.code,
            'instruction': q.instruction_text, 'content': q.content_text,
            'question': q.question_text,
            'media_url': q.media_url, 'media_type': q.media_type,
            'difficulty': q.difficulty, 'points': q.points,
            'time_limit': q.time_limit_seconds,
            'response_format': _normalize_response_format(q.question_type.response_format),
        }

        fmt = _normalize_response_format(q.question_type.response_format)
        if fmt in ('single_choice', 'true_false'):
            data['options'] = list(q.options.values('label', 'text', 'media_url', 'order'))
        elif fmt == 'matching':
            data['pairs'] = list(q.matching_pairs.values('left_text', 'right_text', 'order'))
        elif fmt == 'ordering':
            items = list(q.ordering_items.values('text', 'correct_position'))
            import random
            random.shuffle(items)
            data['items'] = items

        if q.skill.code == 'writing':
            data['answer_samples'] = list(
                q.answer_samples.values('text', 'keywords', 'order')
            )

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
        sublevel_code = data.get('starting_sublevel')
        skill_code = data.get('skill')
        difficulty_tier = data.get('difficulty_tier')
        session_type = data.get('session_type', 'practice')

        candidate, _ = Candidate.objects.get_or_create(
            email=email, defaults={'name': name}
        )

        try:
            engine = AdaptiveEngine(
                candidate, starting_level_code=level,
                skill_code=skill_code, session_type=session_type,
                starting_sublevel_code=sublevel_code,
                difficulty_tier_code=difficulty_tier,
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
            'starting_sublevel': engine.current_sublevel.code if engine.current_sublevel else None,
            'skill': skill_code or 'all',
            'difficulty_tier': difficulty_tier,
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
        skill_code = question.skill.code
        instruction = question.instruction_text or question.question_type.instruction_template
        if skill_code == 'speaking' and not instruction:
            instruction = 'Speak clearly and stay on topic.'

        data = {
            'finished': False,
            'question_id': question.question_id,
            'title': question.title,
            'level': question.cefr_level.code,
            'sublevel': question.sublevel.code if question.sublevel else None,
            'skill': question.skill.code,
            'question_type': question.question_type.code,
            'instruction': instruction,
            'content': question.content_text,
            'question': question.question_text,
            'media_url': question.media_url,
            'media_type': question.media_type,
            'points': question.points,
            'time_limit': question.time_limit_seconds,
            'response_format': _normalize_response_format(question.question_type.response_format),
            'progress': progress,
        }

        # For listening questions: generate TTS audio, hide the transcript
        if skill_code == 'listening':
            tts_text = question.content_text or question.question_text
            # Strip "[Audio transcript]" prefix for clean TTS
            import re
            tts_text = re.sub(r'^\[Audio[^\]]*\]\s*', '', tts_text, flags=re.IGNORECASE)
            audio_b64 = generate_tts_audio(tts_text)
            if audio_b64:
                data['audio_base64'] = audio_b64
                data['audio_format'] = 'mp3'
            # Always send tts_text so frontend can use browser TTS as fallback
            data['tts_text'] = tts_text
            # Don't send the raw transcript — candidate must listen
            data['content'] = None
            data['has_audio'] = True

        # For speaking read-aloud: generate TTS of the passage so candidate
        # can hear the correct pronunciation first (optional playback)
        elif skill_code == 'speaking' and question.question_type.code == 'read_aloud':
            tts_text = question.content_text or question.question_text
            audio_b64 = generate_tts_audio(tts_text)
            if audio_b64:
                data['audio_base64'] = audio_b64
                data['audio_format'] = 'mp3'
            data['tts_text'] = tts_text
            data['has_audio'] = True
            data['requires_microphone'] = True

        # For other speaking questions: needs microphone, no TTS
        elif skill_code == 'speaking':
            data['requires_microphone'] = True

        # Always include speaking_topic for speaking questions (all speaking types)
        if skill_code == 'speaking':
            data['speaking_topic'] = question.speaking_topic or question.question_text or question.title
            data['response_expectation'] = 'audio'

        fmt = _normalize_response_format(question.question_type.response_format)
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
                'starting_sublevel': session.starting_sublevel.code if session.starting_sublevel else None,
                'final_level': session.final_level.code if session.final_level else None,
                'final_sublevel': session.final_sublevel.code if session.final_sublevel else None,
                # Aliases matching finish_session() field names expected by Results.tsx
                'level': session.final_level.code if session.final_level else None,
                'sublevel': session.final_sublevel.code if session.final_sublevel else None,
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
                'level_passed': session.percentage >= 80.0,
                'next_level': (
                    CEFRLevel.objects.filter(order=session.final_level.order + 1).first().code
                    if session.final_level and session.percentage >= 80.0
                    and CEFRLevel.objects.filter(order=session.final_level.order + 1).exists()
                    else None
                ),
                'pass_threshold': 80.0,
            }
        })


# ── Admin Analytics Endpoint ─────────────────────────────────────────

class AdminAnalyticsView(View):
    """Detailed analytics for admin: all candidates, their sessions, performance, and question analysis."""

    def get(self, request):
        from django.db.models import Count, Avg, Q, F

        # Optional filter by candidate email
        candidate_email = request.GET.get('email')

        # Platform-wide stats
        total_candidates = Candidate.objects.count()
        total_sessions = AssessmentSession.objects.count()
        total_questions = Question.objects.filter(is_active=True).count()

        # Average pass rate (sessions with >= 80% score)
        completed_sessions = AssessmentSession.objects.filter(is_completed=True)
        total_completed = completed_sessions.count()
        passed_sessions = 0
        if total_completed > 0:
            for s in completed_sessions:
                if s.percentage >= 80.0:
                    passed_sessions += 1
        avg_pass_rate = round((passed_sessions / total_completed) * 100, 1) if total_completed > 0 else 0

        # Most difficult questions (highest failure rate)
        difficult_questions = []
        question_stats = (
            Response.objects.values('question__question_id', 'question__title', 'question__skill__code')
            .annotate(
                total_attempts=Count('id'),
                failures=Count('id', filter=Q(is_correct=False)),
            )
            .filter(total_attempts__gte=2)
            .order_by('-failures')[:10]
        )
        for qs in question_stats:
            failure_rate = round((qs['failures'] / qs['total_attempts']) * 100, 1) if qs['total_attempts'] > 0 else 0
            difficult_questions.append({
                'question_id': qs['question__question_id'],
                'title': qs['question__title'],
                'skill': qs['question__skill__code'],
                'total_attempts': qs['total_attempts'],
                'failures': qs['failures'],
                'failure_rate': failure_rate,
            })

        # Skill-wise average performance
        skill_performance = []
        for skill in Skill.objects.all().order_by('order'):
            skill_scores_qs = SkillScore.objects.filter(skill=skill)
            if skill_scores_qs.exists():
                avg_pct = skill_scores_qs.aggregate(avg=Avg('percentage'))['avg'] or 0
                skill_performance.append({
                    'skill': skill.name,
                    'skill_code': skill.code,
                    'average_percentage': round(avg_pct, 1),
                    'total_assessments': skill_scores_qs.count(),
                })

        # Per-candidate data
        candidates_data = []
        candidates_qs = Candidate.objects.all().order_by('name')
        if candidate_email:
            candidates_qs = candidates_qs.filter(email=candidate_email)

        for candidate in candidates_qs:
            sessions = AssessmentSession.objects.filter(candidate=candidate).order_by('-started_at')
            session_count = sessions.count()
            completed = sessions.filter(is_completed=True)

            # Overall performance
            overall_pct = 0
            if completed.exists():
                total_score = sum(s.total_score for s in completed)
                total_max = sum(s.max_possible_score for s in completed)
                overall_pct = round((total_score / total_max) * 100, 1) if total_max > 0 else 0

            # Per-skill breakdown
            skill_breakdown = []
            for skill in Skill.objects.all().order_by('order'):
                ss = SkillScore.objects.filter(session__candidate=candidate, skill=skill)
                if ss.exists():
                    avg = ss.aggregate(avg=Avg('percentage'))['avg'] or 0
                    passed_count = sum(1 for s in ss if s.percentage >= 66.7)  # 2/3 threshold
                    skill_breakdown.append({
                        'skill': skill.name,
                        'skill_code': skill.code,
                        'average_percentage': round(avg, 1),
                        'assessments': ss.count(),
                        'passed': passed_count,
                    })

            # Most failed questions for this candidate
            failed_qs = (
                Response.objects.filter(candidate=candidate, is_correct=False)
                .values('question__question_id', 'question__title', 'question__skill__code')
                .annotate(fail_count=Count('id'))
                .order_by('-fail_count')[:5]
            )
            most_failed = [{
                'question_id': fq['question__question_id'],
                'title': fq['question__title'],
                'skill': fq['question__skill__code'],
                'fail_count': fq['fail_count'],
            } for fq in failed_qs]

            # Best performing questions
            best_qs = (
                Response.objects.filter(candidate=candidate, is_correct=True)
                .values('question__question_id', 'question__title', 'question__skill__code')
                .annotate(correct_count=Count('id'))
                .order_by('-correct_count')[:5]
            )
            best_performing = [{
                'question_id': bq['question__question_id'],
                'title': bq['question__title'],
                'skill': bq['question__skill__code'],
                'correct_count': bq['correct_count'],
            } for bq in best_qs]

            # Session history
            session_history = []
            for s in sessions:
                session_history.append({
                    'session_id': str(s.id),
                    'session_type': s.session_type,
                    'starting_level': s.starting_level.code if s.starting_level else None,
                    'final_level': s.final_level.code if s.final_level else None,
                    'total_questions': s.total_questions,
                    'correct_answers': s.correct_answers,
                    'percentage': s.percentage,
                    'is_completed': s.is_completed,
                    'level_passed': s.percentage >= 80.0,
                    'started_at': s.started_at.isoformat() if s.started_at else None,
                    'ended_at': s.ended_at.isoformat() if s.ended_at else None,
                })

            candidates_data.append({
                'name': candidate.name,
                'email': candidate.email,
                'current_level': candidate.current_cefr_level.code if candidate.current_cefr_level else 'A1',
                'total_sessions': session_count,
                'overall_percentage': overall_pct,
                'skill_breakdown': skill_breakdown,
                'most_failed_questions': most_failed,
                'best_performing_questions': best_performing,
                'session_history': session_history,
            })

        return JsonResponse({
            'platform_stats': {
                'total_candidates': total_candidates,
                'total_sessions': total_sessions,
                'total_questions': total_questions,
                'completed_sessions': total_completed,
                'average_pass_rate': avg_pass_rate,
                'pass_threshold': 80.0,
            },
            'difficult_questions': difficult_questions,
            'skill_performance': skill_performance,
            'candidates': candidates_data,
        })


# ── Session Resume Endpoint ──────────────────────────────────────────

class SessionResumeView(View):
    """Check if a candidate has an incomplete session and return its state."""

    def get(self, request):
        email = request.GET.get('email')
        if not email:
            return _json_error('email query parameter is required')

        try:
            candidate = Candidate.objects.get(email=email)
        except Candidate.DoesNotExist:
            return JsonResponse({'has_incomplete_session': False})

        # Find the most recent incomplete session
        incomplete = (
            AssessmentSession.objects.filter(candidate=candidate, is_completed=False)
            .order_by('-started_at')
            .first()
        )

        if not incomplete:
            return JsonResponse({'has_incomplete_session': False})

        session_id = str(incomplete.id)
        engine = _active_engines.get(session_id)

        # Count answered questions in this session
        answered_count = Response.objects.filter(session=incomplete).count()

        # Get skill scores so far
        responses = Response.objects.filter(session=incomplete).select_related('question__skill')
        skill_progress = {}
        for r in responses:
            sk = r.question.skill.code
            if sk not in skill_progress:
                skill_progress[sk] = {'total': 0, 'correct': 0}
            skill_progress[sk]['total'] += 1
            if r.is_correct:
                skill_progress[sk]['correct'] += 1

        result = {
            'has_incomplete_session': True,
            'session_id': session_id,
            'session_type': incomplete.session_type,
            'starting_level': incomplete.starting_level.code if incomplete.starting_level else 'A1',
            'current_level': incomplete.current_level.code if incomplete.current_level else 'A1',
            'questions_answered': answered_count,
            'total_score': incomplete.total_score,
            'max_possible_score': incomplete.max_possible_score,
            'started_at': incomplete.started_at.isoformat() if incomplete.started_at else None,
            'skill_progress': skill_progress,
            'engine_active': engine is not None,
        }

        return JsonResponse(result)


# ── TTS Endpoint ─────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class TTSView(View):
    def post(self, request):
        data = _parse_json(request)
        if not data:
            return _json_error('Invalid JSON body')

        text = data.get('text', '').strip()
        if not text:
            return _json_error('text is required')

        if len(text) > 2000:
            return _json_error('Text too long (max 2000 characters)')

        audio_b64 = generate_tts_audio(text)
        if audio_b64:
            return JsonResponse({
                'audio_base64': audio_b64,
                'audio_format': 'mp3',
            })
        else:
            return _json_error('TTS generation failed. Service may be temporarily unavailable.', 503)
