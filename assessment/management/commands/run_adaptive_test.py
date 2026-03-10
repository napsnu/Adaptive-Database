"""
CLI Interactive Adaptive Assessment Demo.

Runs an adaptive CEFR assessment in the terminal.
Supports all 4 skills and auto-grades objective questions.

Usage:
    python manage.py run_adaptive_test --email test@example.com
    python manage.py run_adaptive_test --email test@example.com --skill reading --level B1
    python manage.py run_adaptive_test --email test@example.com --auto
"""

import random
from django.core.management.base import BaseCommand
from assessment.models import Candidate, CEFRLevel, Skill
from assessment.adaptive_engine import AdaptiveEngine


class Command(BaseCommand):
    help = 'Run an interactive adaptive CEFR assessment in the terminal'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, default='demo@cefr.com',
                            help='Candidate email')
        parser.add_argument('--name', type=str, default='Demo Candidate',
                            help='Candidate name (used for new candidates)')
        parser.add_argument('--level', type=str, default='A1',
                            choices=['A1', 'A2', 'B1', 'B2', 'C1', 'C2'],
                            help='Starting CEFR level')
        parser.add_argument('--skill', type=str, default=None,
                            choices=['reading', 'writing', 'speaking', 'listening'],
                            help='Focus on a specific skill (default: all)')
        parser.add_argument('--auto', action='store_true',
                            help='Auto-answer mode for demo purposes')

    def handle(self, *args, **options):
        email = options['email']
        name = options['name']
        level = options['level']
        skill = options['skill']
        auto = options['auto']

        candidate, created = Candidate.objects.get_or_create(
            email=email, defaults={'name': name}
        )

        self._header(candidate, level, skill, auto, created)

        engine = AdaptiveEngine(
            candidate, starting_level_code=level,
            skill_code=skill, session_type='practice'
        )
        session = engine.start_session()
        self.stdout.write(f'  Session: {str(session.id)[:8]}...\n')

        q_num = 0
        while not engine.is_finished():
            question = engine.get_next_question()
            if not question:
                self.stdout.write(self.style.WARNING('\n  No more questions available at this level.'))
                break

            q_num += 1
            self._display_question(q_num, question, engine)

            fmt = question.question_type.response_format

            if auto:
                result = self._auto_answer(engine, question, fmt)
            else:
                try:
                    result = self._manual_answer(engine, question, fmt)
                except (EOFError, KeyboardInterrupt):
                    self.stdout.write('\n\n  Test aborted by user.')
                    final = engine.finish_session()
                    self._print_results(final)
                    return

            self._display_result(result)

        final = engine.finish_session()
        self._print_results(final)

    def _header(self, candidate, level, skill, auto, created):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING('  ADAPTIVE CEFR ENGLISH ASSESSMENT'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        if created:
            self.stdout.write(self.style.SUCCESS(f'  New candidate: {candidate.name}'))
        else:
            self.stdout.write(f'  Candidate: {candidate.name} ({candidate.email})')
        self.stdout.write(f'  Start Level : {level}')
        self.stdout.write(f'  Skill Focus : {skill or "All Skills"}')
        mode = 'AUTO (simulated)' if auto else 'INTERACTIVE'
        self.stdout.write(f'  Mode        : {mode}')
        self.stdout.write(self.style.MIGRATE_HEADING('-' * 60))

    def _display_question(self, num, question, engine):
        progress = engine.get_progress()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'--- Question {num} ---'))
        self.stdout.write(f'  Level: {question.cefr_level.code} | '
                          f'Skill: {question.skill.name} | '
                          f'Type: {question.question_type.name}')
        self.stdout.write(f'  Topic: {question.topic.name} | '
                          f'Points: {question.points}')
        # Show hierarchical progress
        passed = ', '.join(progress['skills_passed']) if progress['skills_passed'] else 'none'
        self.stdout.write(f'  Current Skill: {progress["current_skill"]} '
                          f'(Q {progress["questions_in_skill"] + 1}/{progress["questions_per_skill"]}) | '
                          f'Attempt: {progress["current_skill_attempt"]}/{progress["max_attempts"]}')
        self.stdout.write(f'  Skills Passed: {passed}')
        self.stdout.write('')

        if question.content_text:
            self.stdout.write(self.style.HTTP_NOT_MODIFIED(f'  {question.content_text}'))
            self.stdout.write('')

        self.stdout.write(f'  QUESTION: {question.question_text}')
        self.stdout.write('')

        fmt = question.question_type.response_format
        if fmt in ('single_choice', 'true_false'):
            for opt in question.options.all():
                self.stdout.write(f'    {opt.label}. {opt.text}')
        elif fmt == 'matching':
            self.stdout.write('  Match the items:')
            pairs = list(question.matching_pairs.all())
            right_shuffled = [p.right_text for p in pairs]
            random.shuffle(right_shuffled)
            for i, pair in enumerate(pairs, 1):
                self.stdout.write(f'    {i}. {pair.left_text}')
            self.stdout.write('  Options:')
            for i, rt in enumerate(right_shuffled, 1):
                self.stdout.write(f'    {i}. {rt}')
        elif fmt == 'ordering':
            items = list(question.ordering_items.all())
            shuffled = items[:]
            random.shuffle(shuffled)
            self.stdout.write('  Put in order:')
            for i, item in enumerate(shuffled, 1):
                self.stdout.write(f'    {i}. {item.text}')

        self.stdout.write('')

    def _manual_answer(self, engine, question, fmt):
        if fmt in ('single_choice', 'true_false'):
            label = input('  Your answer (A/B/C/D): ').strip().upper()
            return engine.submit_answer(question, selected_option_label=label)

        elif fmt == 'text_input':
            text = input('  Your answer: ').strip()
            return engine.submit_answer(question, response_text=text)

        elif fmt in ('long_text', 'audio'):
            if question.skill.code == 'speaking':
                self.stdout.write('  🎤 SPEAKING QUESTION — Type what you would say out loud:')
                text = input('  > ').strip()
                return engine.submit_answer(question, response_text=text)
            else:
                self.stdout.write('  (Type your response, or press Enter to skip)')
                text = input('  > ').strip()
                self.stdout.write('  Rate your response (0.0 to 1.0, e.g. 0.7 for 70%):')
                try:
                    score = float(input('  Score: ').strip())
                except ValueError:
                    score = 0.5
                return engine.submit_answer(question, response_text=text, manual_score=score)

        elif fmt == 'matching':
            self.stdout.write('  Enter matches (e.g. 1=2,2=3,3=1,4=4):')
            raw = input('  Matches: ').strip()
            pairs = {}
            for part in raw.split(','):
                if '=' in part:
                    k, v = part.split('=', 1)
                    pairs[k.strip()] = v.strip()
            return engine.submit_answer(question, response_data={'pairs': pairs})

        elif fmt == 'ordering':
            self.stdout.write('  Enter correct order (e.g. 3,1,2,4,5):')
            raw = input('  Order: ').strip()
            try:
                order = [int(x.strip()) for x in raw.split(',')]
            except ValueError:
                order = []
            return engine.submit_answer(question, response_data={'order': order})

        return engine.submit_answer(question)

    def _auto_answer(self, engine, question, fmt):
        if fmt in ('single_choice', 'true_false'):
            # 70% chance of correct answer
            options = list(question.options.all())
            if random.random() < 0.7:
                correct = [o for o in options if o.is_correct]
                label = correct[0].label if correct else options[0].label
            else:
                wrong = [o for o in options if not o.is_correct]
                label = wrong[0].label if wrong else options[0].label
            self.stdout.write(f'  [AUTO] Selected: {label}')
            return engine.submit_answer(question, selected_option_label=label)

        elif fmt == 'text_input':
            # 60% chance of correct answer
            if random.random() < 0.6:
                text = question.correct_answer.split('|')[0]
            else:
                text = 'wrong answer'
            self.stdout.write(f'  [AUTO] Typed: {text}')
            return engine.submit_answer(question, response_text=text)

        elif fmt in ('long_text', 'audio'):
            if question.skill.code == 'speaking':
                # Simulate spoken response - use sample_answer or generate words
                if question.question_type.code == 'read_aloud' and question.content_text:
                    # For read-aloud, "speak" the passage text (with some errors)
                    words = question.content_text.split()
                    if random.random() < 0.7:
                        text = question.content_text  # Good reading
                    else:
                        text = ' '.join(words[:len(words)//2])  # Partial reading
                else:
                    # For opinion/describe, generate some words
                    word_count = random.randint(10, 40)
                    text = ' '.join(['sample'] * word_count)
                self.stdout.write(f'  [AUTO] Spoke: {text[:80]}...')
                return engine.submit_answer(question, response_text=text)
            else:
                score = round(random.uniform(0.3, 0.9), 1)
                self.stdout.write(f'  [AUTO] Manual score: {score}')
                return engine.submit_answer(question, response_text='Auto response', manual_score=score)

        elif fmt == 'matching':
            pairs = list(question.matching_pairs.all())
            match_data = {}
            for i in range(len(pairs)):
                if random.random() < 0.7:
                    match_data[str(i + 1)] = str(i + 1)
                else:
                    match_data[str(i + 1)] = str(random.randint(1, len(pairs)))
            self.stdout.write(f'  [AUTO] Matches: {match_data}')
            return engine.submit_answer(question, response_data={'pairs': match_data})

        elif fmt == 'ordering':
            items = list(question.ordering_items.all())
            if random.random() < 0.5:
                order = [item.correct_position for item in items]
            else:
                order = list(range(1, len(items) + 1))
                random.shuffle(order)
            self.stdout.write(f'  [AUTO] Order: {order}')
            return engine.submit_answer(question, response_data={'order': order})

        return engine.submit_answer(question)

    def _display_result(self, result):
        if result['is_correct']:
            self.stdout.write(self.style.SUCCESS(f'  >>> CORRECT! +{result["score"]} points'))
        else:
            self.stdout.write(self.style.ERROR(f'  >>> INCORRECT. {result["feedback"][:100]}'))

        action = result['action']
        skill_status = result.get('skill_status')

        if action == 'SKILL_PASSED' and skill_status:
            self.stdout.write(self.style.SUCCESS(
                f'  ★ {skill_status["message"]}'
            ))
            if skill_status.get('next_skill'):
                self.stdout.write(self.style.SUCCESS(
                    f'  → Next skill: {skill_status["next_skill"].title()}'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'  ★★ All skills complete for this level!'
                ))
        elif action == 'SKILL_FAILED_RETRY' and skill_status:
            self.stdout.write(self.style.WARNING(
                f'  ✗ {skill_status["message"]}'
            ))
        elif action == 'SKILL_FAILED_MAX_RETRIES' and skill_status:
            self.stdout.write(self.style.ERROR(
                f'  ✗ {skill_status["message"]}'
            ))
        else:
            self.stdout.write(
                f'  Progress: {result["skill_progress"]} | '
                f'Skill: {result["current_skill"]} | '
                f'Total: {result["total_correct"]}/{result["total_questions"]} correct'
            )

    def _print_results(self, result):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING('  ASSESSMENT COMPLETE'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(f'  Session       : {result["session_id"][:8]}...')
        self.stdout.write(f'  Candidate     : {result["candidate"]}')
        self.stdout.write(f'  Level         : {result["level"]}')
        level_status = 'PASSED' if result['level_passed'] else 'NOT PASSED'
        self.stdout.write(self.style.SUCCESS(
            f'  Level Status  : {level_status}'
        ))
        if result.get('next_level'):
            self.stdout.write(self.style.SUCCESS(
                f'  Next Level    : {result["next_level"]} UNLOCKED!'
            ))
        self.stdout.write(f'  Questions     : {result["total_questions"]}')
        self.stdout.write(f'  Correct       : {result["total_correct"]}')
        self.stdout.write(f'  Score         : {result["total_score"]}/{result["max_possible_score"]}')
        self.stdout.write(f'  Percentage    : {result["percentage"]}%')

        # Skill breakdown
        self.stdout.write('')
        self.stdout.write('  Skill Results:')
        for skill_code, info in result.get('skill_results', {}).items():
            status = 'PASSED' if info['passed'] else 'FAILED'
            scores = ', '.join(info['scores']) if info['scores'] else 'N/A'
            style = self.style.SUCCESS if info['passed'] else self.style.ERROR
            self.stdout.write(style(
                f'    {skill_code.title():12s} : {status} (Attempts: {info["attempts"]}, Scores: {scores})'
            ))

        self.stdout.write('')
        self.stdout.write('  Question-by-question:')
        for h in result['history']:
            mark = 'OK' if h['is_correct'] else 'XX'
            self.stdout.write(
                f'    [{mark}] {h["question_id"]:20s} | '
                f'+{h["score"]:.0f}/{h["max_score"]:.0f} | '
                f'Skill: {h.get("current_skill", "?")} | {h["action"]}'
            )
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
