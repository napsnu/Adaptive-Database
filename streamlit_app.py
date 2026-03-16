"""
Streamlit Demo App for the Adaptive CEFR English Learning Platform.

Features:
  - Full adaptive assessment (Reading -> Writing -> Speaking -> Listening)
  - Real TTS audio playback for listening questions
  - Speech-to-text input for speaking questions (type-to-simulate in Streamlit)
  - AI grading (Gemini) with basic fallback
  - Live progress tracking and skill transitions
  - Results dashboard with per-skill breakdown

Run:
    streamlit run streamlit_app.py
"""

import os
import sys
import re
import base64
import random

# ── Django Setup ─────────────────────────────────────────────────────
# Must happen before any Django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adaptive_cefr.settings')

import django
django.setup()

import streamlit as st
from assessment.models import (
    CEFRLevel, Skill, Question, QuestionOption,
    MatchingPair, OrderingItem, Candidate, AssessmentSession,
)
from assessment.adaptive_engine import AdaptiveEngine
from assessment.ai_services import generate_tts_audio, grade_with_gemini

# ── Page Config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="CEFR English Assessment",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Skill Icons ──────────────────────────────────────────────────────
SKILL_ICONS = {
    'reading': '📖',
    'writing': '✍️',
    'speaking': '🎤',
    'listening': '🎧',
}

SKILL_COLORS = {
    'reading': '#3B82F6',
    'writing': '#8B5CF6',
    'speaking': '#EF4444',
    'listening': '#F59E0B',
}


# ── Session State Helpers ────────────────────────────────────────────
def init_state():
    """Initialize session state defaults."""
    defaults = {
        'page': 'home',
        'engine': None,
        'session': None,
        'current_question': None,
        'question_number': 0,
        'last_result': None,
        'show_skill_modal': False,
        'skill_modal_data': None,
        'candidate_name': '',
        'candidate_email': '',
        'selected_level': 'A1',
        'assessment_history': [],
        'tts_audio_b64': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def go_to(page):
    st.session_state.page = page
    st.session_state.last_result = None
    st.session_state.show_skill_modal = False


# ── Custom CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
    .skill-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        color: white;
        font-weight: 600;
        font-size: 14px;
        margin: 2px 4px;
    }
    .progress-step {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 8px;
        margin: 0 4px;
        font-weight: 600;
        font-size: 13px;
    }
    .step-active { background: #3B82F6; color: white; }
    .step-passed { background: #22C55E; color: white; }
    .step-failed { background: #EF4444; color: white; }
    .step-pending { background: #E5E7EB; color: #6B7280; }
    .big-metric {
        text-align: center;
        padding: 20px;
        border-radius: 12px;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
    }
    .big-metric h1 { margin: 0; font-size: 48px; }
    .big-metric p { margin: 4px 0 0; color: #64748B; font-size: 14px; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# PAGES
# ═════════════════════════════════════════════════════════════════════

def page_home():
    """Landing / Home page."""
    st.markdown("## 📚 Adaptive CEFR English Assessment Platform")
    st.markdown("Test your English skills across **Reading**, **Writing**, **Speaking**, and **Listening** with AI-powered adaptive assessment.")

    st.divider()

    # Quick stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        count = CEFRLevel.objects.count()
        st.metric("CEFR Levels", count)
    with col2:
        count = Question.objects.filter(is_active=True).count()
        st.metric("Questions", count)
    with col3:
        st.metric("Skills", "4")
    with col4:
        st.metric("AI Grading", "Gemini")

    st.divider()

    # How it works
    st.markdown("### How It Works")
    cols = st.columns(4)
    steps = [
        ("📖 Reading", "Comprehension, fill-in-gaps, true/false"),
        ("✍️ Writing", "Short answers, essays, gap-fill"),
        ("🎤 Speaking", "Read aloud, describe, give opinions"),
        ("🎧 Listening", "Audio playback, comprehension questions"),
    ]
    for col, (title, desc) in zip(cols, steps):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)

    st.info("**Flow:** You pick a level (A1-C2). The engine tests all 4 skills in order. "
            "Pass 2/3 questions per skill to advance. Fail? You get up to 3 attempts.")

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        if st.button("🚀 Start Assessment", type="primary", use_container_width=True):
            go_to('setup')
            st.rerun()
    with col_right:
        if st.button("📊 View Question Bank", use_container_width=True):
            go_to('questions')
            st.rerun()


def page_setup():
    """Candidate info + level selection."""
    st.markdown("## 🎯 Start Your Assessment")
    st.markdown("Enter your details and select a CEFR level to begin.")

    with st.form("setup_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your Name", value=st.session_state.candidate_name or "")
        with col2:
            email = st.text_input("Your Email", value=st.session_state.candidate_email or "")

        st.divider()
        st.markdown("### Select CEFR Level")

        levels = list(CEFRLevel.objects.all().order_by('order'))
        level_options = {f"{lv.code} - {lv.name}": lv.code for lv in levels}
        selected = st.selectbox("Level", list(level_options.keys()))

        # Show level descriptions
        for lv in levels:
            if f"{lv.code} - {lv.name}" == selected:
                if lv.description:
                    st.caption(lv.description)
                q_count = Question.objects.filter(cefr_level=lv, is_active=True).count()
                st.caption(f"Questions available: {q_count}")
                break

        st.divider()
        st.markdown("**Assessment Flow:** Reading → Writing → Speaking → Listening (3 questions each)")

        submitted = st.form_submit_button("Begin Assessment", type="primary", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("Please enter your name.")
            elif not email.strip():
                st.error("Please enter your email.")
            else:
                st.session_state.candidate_name = name.strip()
                st.session_state.candidate_email = email.strip()
                st.session_state.selected_level = level_options[selected]
                _start_assessment()
                st.rerun()

    if st.button("← Back to Home"):
        go_to('home')
        st.rerun()


def _start_assessment():
    """Initialize the adaptive engine and start a session."""
    candidate, _ = Candidate.objects.get_or_create(
        email=st.session_state.candidate_email,
        defaults={'name': st.session_state.candidate_name}
    )

    engine = AdaptiveEngine(
        candidate,
        starting_level_code=st.session_state.selected_level,
        session_type='practice',
    )
    session = engine.start_session()

    st.session_state.engine = engine
    st.session_state.session = session
    st.session_state.current_question = None
    st.session_state.question_number = 0
    st.session_state.last_result = None
    st.session_state.show_skill_modal = False
    st.session_state.tts_audio_b64 = None
    st.session_state.page = 'assessment'


def page_assessment():
    """Main assessment page — displays questions and handles answers."""
    engine = st.session_state.engine
    if not engine:
        st.error("No active session. Please start a new assessment.")
        if st.button("Start New Assessment"):
            go_to('setup')
            st.rerun()
        return

    # ── Show skill transition modal ──────────────────────────────
    if st.session_state.show_skill_modal and st.session_state.skill_modal_data:
        _show_skill_modal()
        return

    # ── Check if finished ────────────────────────────────────────
    if engine.is_finished():
        go_to('results')
        st.rerun()
        return

    # ── Get next question ────────────────────────────────────────
    if st.session_state.current_question is None:
        q = engine.get_next_question()
        if q is None:
            go_to('results')
            st.rerun()
            return
        st.session_state.current_question = q
        st.session_state.question_number += 1
        # Generate TTS for listening
        if q.skill.code == 'listening':
            tts_text = q.content_text or q.question_text
            tts_text = re.sub(r'^\[Audio[^\]]*\]\s*', '', tts_text, flags=re.IGNORECASE)
            audio_b64 = generate_tts_audio(tts_text)
            st.session_state.tts_audio_b64 = audio_b64
            st.session_state.tts_text = tts_text
        elif q.skill.code == 'speaking' and q.question_type.code == 'read_aloud':
            tts_text = q.content_text or q.question_text
            audio_b64 = generate_tts_audio(tts_text)
            st.session_state.tts_audio_b64 = audio_b64
            st.session_state.tts_text = tts_text
        else:
            st.session_state.tts_audio_b64 = None
            st.session_state.tts_text = None

    question = st.session_state.current_question
    progress = engine.get_progress()

    # ── Progress Bar ─────────────────────────────────────────────
    _render_progress_bar(progress)

    # ── Question Header ──────────────────────────────────────────
    skill_code = question.skill.code
    icon = SKILL_ICONS.get(skill_code, '📝')

    st.markdown(f"### {icon} Question {st.session_state.question_number}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"**Level:** {question.cefr_level.code}")
    with col2:
        st.caption(f"**Skill:** {question.skill.name}")
    with col3:
        st.caption(f"**Type:** {question.question_type.name} | **Points:** {question.points}")

    attempt_info = f"Attempt {progress['current_skill_attempt']}/{progress['max_attempts']}"
    q_in_skill = f"Question {progress['questions_in_skill'] + 1}/{progress['questions_per_skill']}"
    st.caption(f"{q_in_skill} in {question.skill.name} | {attempt_info}")

    st.divider()

    # ── Last result feedback ─────────────────────────────────────
    if st.session_state.last_result:
        r = st.session_state.last_result
        if r['is_correct']:
            st.success(f"✅ Previous answer correct! +{r['score']} points — {r['feedback']}")
        else:
            st.error(f"❌ Previous answer incorrect — {r['feedback']}")
        st.session_state.last_result = None

    # ── Render question by skill type ────────────────────────────
    if skill_code == 'listening':
        _render_listening_question(question)
    elif skill_code == 'speaking':
        _render_speaking_question(question)
    else:
        _render_standard_question(question)


def _render_progress_bar(progress):
    """Render the skill progression bar at the top."""
    skill_order = progress.get('skill_order', ['reading', 'writing', 'speaking', 'listening'])
    current_skill = progress.get('current_skill')
    passed = set(progress.get('skills_passed', []))
    failed = set(progress.get('skills_failed', []))

    cols = st.columns(len(skill_order))
    for i, (col, skill) in enumerate(zip(cols, skill_order)):
        icon = SKILL_ICONS.get(skill, '📝')
        with col:
            if skill in passed:
                st.markdown(f"<div class='progress-step step-passed'>✅ {icon} {skill.title()}</div>",
                            unsafe_allow_html=True)
            elif skill in failed and skill != current_skill:
                st.markdown(f"<div class='progress-step step-failed'>❌ {icon} {skill.title()}</div>",
                            unsafe_allow_html=True)
            elif skill == current_skill:
                st.markdown(f"<div class='progress-step step-active'>▶ {icon} {skill.title()}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='progress-step step-pending'>{icon} {skill.title()}</div>",
                            unsafe_allow_html=True)


def _render_listening_question(question):
    """Render a listening question with audio playback."""
    st.markdown("#### 🎧 Listening Question")
    st.info("Listen to the audio carefully, then answer the question below. "
            "In a real exam, the text would be hidden — you must rely on listening only.")

    # Audio playback
    audio_b64 = st.session_state.tts_audio_b64
    tts_text = getattr(st.session_state, 'tts_text', None)

    if audio_b64:
        audio_bytes = base64.b64decode(audio_b64)
        st.audio(audio_bytes, format='audio/mp3')
        st.caption("🔊 Click play to listen. You can replay as needed for this demo.")
    elif tts_text:
        st.warning("⚠️ Backend TTS unavailable. Showing transcript for this demo session.")
        with st.expander("📝 Audio Transcript (would be hidden in real exam)", expanded=True):
            st.write(tts_text)
    else:
        # Show transcript as fallback
        if question.content_text:
            transcript = re.sub(r'^\[Audio[^\]]*\]\s*', '', question.content_text, flags=re.IGNORECASE)
            st.warning("⚠️ TTS unavailable. Showing transcript:")
            st.write(transcript)

    st.divider()
    st.markdown(f"**{question.question_text}**")

    # Answer input based on format
    _render_answer_input(question)


def _render_speaking_question(question):
    """Render a speaking question with microphone simulation."""
    st.markdown("#### 🎤 Speaking Question")

    instruction = (
        question.instruction_text
        or question.question_type.instruction_template
        or "Speak clearly and stay on topic."
    )
    speaking_topic = (
        getattr(question, "speaking_topic", None)
        or question.question_text
        or question.title
        or "Please answer the prompt aloud."
    )

    st.markdown("### Speaking Prompt")
    st.info(speaking_topic)
    st.caption(f"Instruction: {instruction}")
    st.caption("Expected response: Spoken answer (microphone)")
    st.divider()

    if question.question_type.code == 'read_aloud':
        st.info("In a real assessment, you would **speak into a microphone**. "
                "The AI grades your pronunciation, accuracy, and fluency. "
                "For this demo, type what you would say.")

        # Show passage to read
        if question.content_text:
            st.markdown("**Read this passage aloud:**")
            st.markdown(f"> {question.content_text}")

        # Optional: play reference pronunciation
        audio_b64 = st.session_state.tts_audio_b64
        if audio_b64:
            st.caption("🔊 Reference pronunciation (listen first, then speak):")
            audio_bytes = base64.b64decode(audio_b64)
            st.audio(audio_bytes, format='audio/mp3')

    else:
        st.info("In a real assessment, you would **speak your answer into a microphone**. "
                "For this demo, type your spoken response.")

        if question.content_text:
            st.markdown(f"*{question.content_text}*")

    st.divider()
    if question.question_text:
        st.markdown(f"**{question.question_text}**")

    # Speaking input — text area simulating microphone
    with st.form(f"speaking_{question.question_id}"):
        response = st.text_area(
            "🎤 Your spoken response (type what you would say):",
            height=120,
            placeholder="Type your response here... In the web app, this would be voice-recorded.",
            key=f"speak_input_{question.question_id}",
        )
        submitted = st.form_submit_button("Submit Response", type="primary", use_container_width=True)

        if submitted:
            if not response.strip():
                st.error("Please enter your response.")
            else:
                _submit_answer(question, response_text=response.strip())
                st.rerun()


def _render_standard_question(question):
    """Render reading/writing questions."""
    # Content/passage
    if question.content_text:
        st.markdown(f"*{question.content_text}*")
        st.divider()

    st.markdown(f"**{question.question_text}**")

    _render_answer_input(question)


def _render_answer_input(question):
    """Render the answer input widget based on response format."""
    fmt = question.question_type.response_format

    if fmt in ('single_choice', 'true_false'):
        options = list(question.options.all().order_by('order'))
        if not options:
            st.warning("No options available for this question.")
            return

        with st.form(f"choice_{question.question_id}"):
            choices = {f"{opt.label}. {opt.text}": opt.label for opt in options}
            selected = st.radio("Select your answer:", list(choices.keys()),
                                key=f"radio_{question.question_id}")
            submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)

            if submitted:
                label = choices[selected]
                _submit_answer(question, selected_option_label=label)
                st.rerun()

    elif fmt == 'text_input':
        with st.form(f"text_{question.question_id}"):
            answer = st.text_input("Your answer:", key=f"text_input_{question.question_id}")
            submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)

            if submitted:
                if not answer.strip():
                    st.error("Please enter an answer.")
                else:
                    _submit_answer(question, response_text=answer.strip())
                    st.rerun()

    elif fmt in ('long_text', 'audio'):
        with st.form(f"long_{question.question_id}"):
            answer = st.text_area(
                "Your response:",
                height=150,
                key=f"long_input_{question.question_id}",
                placeholder="Write your response here..."
            )
            submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)

            if submitted:
                if not answer.strip():
                    st.error("Please enter a response.")
                else:
                    _submit_answer(question, response_text=answer.strip())
                    st.rerun()

    elif fmt == 'matching':
        pairs = list(question.matching_pairs.all().order_by('order'))
        if not pairs:
            st.warning("No matching pairs available.")
            return

        right_texts = [p.right_text for p in pairs]
        shuffled_right = right_texts[:]
        random.shuffle(shuffled_right)

        with st.form(f"match_{question.question_id}"):
            st.markdown("**Match each item on the left with the correct item on the right:**")
            user_matches = {}
            for i, pair in enumerate(pairs):
                selected = st.selectbox(
                    f"{i + 1}. {pair.left_text}",
                    options=shuffled_right,
                    key=f"match_{question.question_id}_{i}"
                )
                user_matches[str(i + 1)] = str(shuffled_right.index(selected) + 1)

            submitted = st.form_submit_button("Submit Matches", type="primary", use_container_width=True)
            if submitted:
                _submit_answer(question, response_data={'pairs': user_matches})
                st.rerun()

    elif fmt == 'ordering':
        items = list(question.ordering_items.all())
        shuffled = items[:]
        random.shuffle(shuffled)

        with st.form(f"order_{question.question_id}"):
            st.markdown("**Put these items in the correct order:**")
            st.caption("Enter the correct position number for each item (1, 2, 3...)")

            user_order = []
            for i, item in enumerate(shuffled):
                pos = st.number_input(
                    f"'{item.text}'",
                    min_value=1, max_value=len(items), value=i + 1,
                    key=f"order_{question.question_id}_{i}"
                )
                user_order.append(pos)

            submitted = st.form_submit_button("Submit Order", type="primary", use_container_width=True)
            if submitted:
                _submit_answer(question, response_data={'order': user_order})
                st.rerun()

    else:
        st.warning(f"Unknown response format: {fmt}")


def _submit_answer(question, selected_option_label=None, response_text='',
                   response_data=None):
    """Submit an answer through the engine and handle the result."""
    engine = st.session_state.engine

    result = engine.submit_answer(
        question,
        selected_option_label=selected_option_label,
        response_text=response_text,
        response_data=response_data,
    )

    st.session_state.last_result = result
    st.session_state.current_question = None
    st.session_state.tts_audio_b64 = None

    # Check for skill transition
    action = result.get('action', 'CONTINUE')
    if action in ('SKILL_PASSED', 'SKILL_FAILED_RETRY', 'SKILL_FAILED_MAX_RETRIES'):
        st.session_state.show_skill_modal = True
        st.session_state.skill_modal_data = {
            'action': action,
            'result': result,
            'skill_status': result.get('skill_status', {}),
        }


def _show_skill_modal():
    """Show a skill transition dialog."""
    data = st.session_state.skill_modal_data
    action = data['action']
    status = data.get('skill_status', {})
    result = data['result']

    skill_name = status.get('skill', '').title()
    score = status.get('score', '')
    message = status.get('message', '')
    next_skill = status.get('next_skill')

    # Last answer feedback
    if result['is_correct']:
        st.success(f"✅ Correct! +{result['score']} points — {result['feedback']}")
    else:
        st.error(f"❌ Incorrect — {result['feedback']}")

    st.divider()

    if action == 'SKILL_PASSED':
        st.balloons()
        st.markdown(f"## ✅ {skill_name} — PASSED!")
        st.markdown(f"**Score: {score}**")
        st.success(message)
        if next_skill:
            icon = SKILL_ICONS.get(next_skill, '📝')
            btn_label = f"Continue to {icon} {next_skill.title()}"
        else:
            btn_label = "View Results"

    elif action == 'SKILL_FAILED_RETRY':
        st.markdown(f"## ⚠️ {skill_name} — Retry Needed")
        st.markdown(f"**Score: {score}**")
        st.warning(message)
        btn_label = f"Retry {skill_name}"

    elif action == 'SKILL_FAILED_MAX_RETRIES':
        st.markdown(f"## ❌ {skill_name} — Not Passed")
        st.markdown(f"**Score: {score}**")
        st.error(message)
        if next_skill:
            icon = SKILL_ICONS.get(next_skill, '📝')
            btn_label = f"Continue to {icon} {next_skill.title()}"
        else:
            btn_label = "View Results"

    else:
        btn_label = "Continue"

    if st.button(btn_label, type="primary", use_container_width=True):
        st.session_state.show_skill_modal = False
        st.session_state.skill_modal_data = None
        st.session_state.last_result = None

        engine = st.session_state.engine
        if engine and engine.is_finished():
            go_to('results')
        st.rerun()


def page_results():
    """Show final assessment results."""
    engine = st.session_state.engine
    if not engine:
        st.error("No session data found.")
        if st.button("Start New Assessment"):
            go_to('setup')
            st.rerun()
        return

    final = engine.finish_session()

    # Save to history
    st.session_state.assessment_history.append(final)

    st.markdown("## 📊 Assessment Results")
    st.divider()

    # Level result
    level = final['level']
    passed = final['level_passed']

    if passed:
        st.success(f"## 🎉 Level {level}: PASSED!")
        if final.get('next_level'):
            st.info(f"🔓 **{final['next_level']}** Unlocked! You can now attempt the next level.")
    else:
        st.error(f"## Level {level}: NOT PASSED")
        st.info("Keep practicing! You can retry this level anytime.")

    # Summary metrics
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Questions", final['total_questions'])
    with col2:
        st.metric("Correct Answers", final['total_correct'])
    with col3:
        st.metric("Score", f"{final['total_score']}/{final['max_possible_score']}")
    with col4:
        st.metric("Percentage", f"{final['percentage']}%")

    # Skill breakdown
    st.divider()
    st.markdown("### Per-Skill Results")

    skill_results = final.get('skill_results', {})
    cols = st.columns(len(skill_results))

    for col, (skill_code, info) in zip(cols, skill_results.items()):
        with col:
            icon = SKILL_ICONS.get(skill_code, '📝')
            sk_passed = info['passed']
            status_emoji = "✅" if sk_passed else "❌"
            scores_str = ", ".join(info['scores']) if info['scores'] else "N/A"

            st.markdown(f"### {icon} {skill_code.title()}")
            st.markdown(f"**{status_emoji} {'PASSED' if sk_passed else 'FAILED'}**")
            st.caption(f"Attempts: {info['attempts']}")
            st.caption(f"Scores: {scores_str}")

            if info['attempts'] > 1 and sk_passed:
                st.caption(f"✨ Passed on attempt {info['attempts']}")

    # Question-by-question breakdown
    st.divider()
    st.markdown("### Question-by-Question Breakdown")

    for h in final.get('history', []):
        mark = "✅" if h['is_correct'] else "❌"
        action = h.get('action', 'CONTINUE')
        action_badge = ""
        if action == 'SKILL_PASSED':
            action_badge = " 🏆"
        elif action == 'SKILL_FAILED_RETRY':
            action_badge = " 🔄"
        elif action == 'SKILL_FAILED_MAX_RETRIES':
            action_badge = " ⛔"

        skill = h.get('current_skill', '?')
        icon = SKILL_ICONS.get(skill, '')
        st.markdown(
            f"{mark} **{h['question_id']}** — "
            f"+{h['score']:.0f}/{h['max_score']:.0f} pts | "
            f"{icon} {skill}{action_badge}"
        )

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        if passed and final.get('next_level'):
            if st.button(f"🚀 Try {final['next_level']}", type="primary", use_container_width=True):
                st.session_state.selected_level = final['next_level']
                st.session_state.engine = None
                st.session_state.current_question = None
                st.session_state.question_number = 0
                go_to('setup')
                st.rerun()
    with col2:
        if st.button("🔄 Retry This Level", use_container_width=True):
            st.session_state.engine = None
            st.session_state.current_question = None
            st.session_state.question_number = 0
            go_to('setup')
            st.rerun()
    with col3:
        if st.button("🏠 Back to Home", use_container_width=True):
            st.session_state.engine = None
            st.session_state.current_question = None
            go_to('home')
            st.rerun()


def page_questions():
    """Question bank browser (admin-like view)."""
    st.markdown("## 📋 Question Bank")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        levels = ['All'] + list(CEFRLevel.objects.values_list('code', flat=True))
        level_filter = st.selectbox("Level", levels, key="qb_level")
    with col2:
        skills = ['All'] + list(Skill.objects.values_list('code', flat=True))
        skill_filter = st.selectbox("Skill", skills, key="qb_skill")
    with col3:
        search = st.text_input("Search", key="qb_search", placeholder="Search questions...")

    qs = Question.objects.filter(is_active=True).select_related(
        'cefr_level', 'skill', 'question_type', 'topic'
    )
    if level_filter != 'All':
        qs = qs.filter(cefr_level__code=level_filter)
    if skill_filter != 'All':
        qs = qs.filter(skill__code=skill_filter)
    if search:
        qs = qs.filter(question_text__icontains=search)

    questions_list = list(qs[:100])

    st.caption(f"Showing {len(questions_list)} questions")

    for q in questions_list:
        icon = SKILL_ICONS.get(q.skill.code, '📝')
        with st.expander(f"{icon} [{q.question_id}] {q.title} — {q.cefr_level.code} | {q.skill.name} | {q.question_type.name}"):
            if q.content_text:
                st.markdown(f"*{q.content_text[:300]}*")
            st.markdown(f"**{q.question_text}**")
            st.caption(f"Points: {q.points} | Difficulty: {q.difficulty} | Topic: {q.topic.name}")

            # Show options
            if q.question_type.response_format in ('single_choice', 'true_false'):
                for opt in q.options.all():
                    mark = "✅" if opt.is_correct else "◻️"
                    st.markdown(f"  {mark} {opt.label}. {opt.text}")

            if q.correct_answer:
                st.caption(f"Correct answer: {q.correct_answer}")

    if st.button("← Back to Home"):
        go_to('home')
        st.rerun()


def page_history():
    """Show assessment history from this session."""
    st.markdown("## 📜 Assessment History")

    history = st.session_state.assessment_history
    if not history:
        st.info("No assessments completed yet in this session.")
        if st.button("Start an Assessment"):
            go_to('setup')
            st.rerun()
        return

    for i, result in enumerate(reversed(history), 1):
        level = result['level']
        passed = result['level_passed']
        status = "✅ PASSED" if passed else "❌ NOT PASSED"
        pct = result['percentage']

        with st.expander(f"Assessment {len(history) - i + 1}: Level {level} — {status} ({pct}%)", expanded=(i == 1)):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Questions", result['total_questions'])
            with col2:
                st.metric("Correct", result['total_correct'])
            with col3:
                st.metric("Score", f"{result['percentage']}%")

            for sk, info in result.get('skill_results', {}).items():
                icon = SKILL_ICONS.get(sk, '')
                status_mark = "✅" if info['passed'] else "❌"
                scores = ", ".join(info['scores']) if info['scores'] else "N/A"
                st.markdown(f"  {icon} {sk.title()}: {status_mark} (Attempts: {info['attempts']}, Scores: {scores})")

    if st.button("← Back to Home"):
        go_to('home')
        st.rerun()


def page_services():
    """Test AI services (TTS + Gemini)."""
    st.markdown("## 🔧 AI Service Diagnostics")
    st.markdown("Test whether TTS and Gemini AI grading services are working.")

    from django.conf import settings

    col1, col2 = st.columns(2)
    with col1:
        hf_key = settings.HUGGINGFACE_API_KEY
        if hf_key:
            st.success(f"HuggingFace Key: Set ({hf_key[:6]}...{hf_key[-4:]})")
        else:
            st.error("HuggingFace Key: NOT SET")
    with col2:
        gemini_key = settings.GEMINI_API_KEY
        if gemini_key:
            st.success(f"Gemini Key: Set ({gemini_key[:6]}...{gemini_key[-4:]})")
        else:
            st.error("Gemini Key: NOT SET")

    st.divider()

    # TTS Test
    st.markdown("### 🔊 TTS Test (Kokoro-82M)")
    test_text = st.text_input("Text to convert to speech:",
                              value="Hello, this is a test of the text to speech system.",
                              key="tts_test_text")
    if st.button("Generate Audio", key="tts_btn"):
        with st.spinner("Generating audio..."):
            audio_b64 = generate_tts_audio(test_text)
        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            st.audio(audio_bytes, format='audio/mp3')
            st.success(f"TTS: OK ({len(audio_b64)} chars base64, ~{len(audio_b64) * 3 // 4 // 1024} KB)")
        else:
            st.error("TTS: FAILED — Check HuggingFace API key & permissions")

    st.divider()

    # Gemini Test
    st.markdown("### 🤖 Gemini Grading Test")
    if st.button("Test Gemini Grading", key="gemini_btn"):
        with st.spinner("Calling Gemini API..."):
            result = grade_with_gemini(
                question_text="Read this passage aloud.",
                response_text="Tom lives in a small house near the park.",
                skill_code='speaking',
                question_type_code='read_aloud',
                cefr_level='A1',
                max_score=2.0,
                expected_text="Tom lives in a small house near the park.",
            )
        if result:
            is_correct, score, feedback = result
            st.success(f"Gemini: OK — {'CORRECT' if is_correct else 'INCORRECT'}, Score: {score}/2.0")
            st.info(f"Feedback: {feedback}")
        else:
            st.error("Gemini: FAILED — API key issue or rate limit exceeded")

    if st.button("← Back to Home"):
        go_to('home')
        st.rerun()


# ═════════════════════════════════════════════════════════════════════
# SIDEBAR + ROUTING
# ═════════════════════════════════════════════════════════════════════
def main():
    # Sidebar
    with st.sidebar:
        st.markdown("## 📚 CEFR Platform")
        st.divider()

        if st.button("🏠 Home", use_container_width=True):
            go_to('home')
            st.rerun()
        if st.button("🎯 Start Assessment", use_container_width=True):
            go_to('setup')
            st.rerun()
        if st.button("📋 Question Bank", use_container_width=True):
            go_to('questions')
            st.rerun()
        if st.button("📜 History", use_container_width=True):
            go_to('history')
            st.rerun()
        if st.button("🔧 AI Diagnostics", use_container_width=True):
            go_to('services')
            st.rerun()

        st.divider()

        # Active session info
        if st.session_state.engine and not st.session_state.engine.is_finished():
            engine = st.session_state.engine
            progress = engine.get_progress()
            st.markdown("### Active Session")
            st.caption(f"Level: {progress['current_level']}")
            st.caption(f"Skill: {progress['current_skill'] or 'Complete'}")
            st.caption(f"Questions: {progress['total_questions']}")
            st.caption(f"Correct: {progress['total_correct']}")
            passed = progress.get('skills_passed', [])
            if passed:
                st.caption(f"Passed: {', '.join(s.title() for s in passed)}")

            if st.button("🚨 End Session", use_container_width=True, type="secondary"):
                go_to('results')
                st.rerun()

        st.divider()
        st.caption("Adaptive CEFR English Platform")
        st.caption("AI: Gemini 2.0 Flash | TTS: Kokoro-82M")

    # Page routing
    page = st.session_state.page
    if page == 'home':
        page_home()
    elif page == 'setup':
        page_setup()
    elif page == 'assessment':
        page_assessment()
    elif page == 'results':
        page_results()
    elif page == 'questions':
        page_questions()
    elif page == 'history':
        page_history()
    elif page == 'services':
        page_services()
    else:
        page_home()


if __name__ == '__main__':
    main()
