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
    MatchingPair, OrderingItem, Candidate, AssessmentSession, SkillScore,
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
        'assessment_history': [],
        'tts_audio_b64': None,
        'candidate': None,
        'question_retry_pending': False,
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
    """Login / landing page — redirects to dashboard if already signed in."""
    if st.session_state.candidate:
        go_to('dashboard')
        st.rerun()
        return

    st.markdown("## 📚 CEFR Mastery Hub")
    st.markdown("Adaptive English Learning Platform — test all 4 skills with AI-powered adaptive assessment.")
    st.divider()

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        with st.form("login_form"):
            st.markdown("### 🔑 Sign In")
            name = st.text_input("Full Name", placeholder="Enter your name")
            email = st.text_input("Email", placeholder="your@email.com")
            submitted = st.form_submit_button("Continue →", type="primary", use_container_width=True)
            if submitted:
                if not name.strip() or not email.strip():
                    st.error("Please enter both name and email.")
                else:
                    candidate, _ = Candidate.objects.get_or_create(
                        email=email.strip().lower(),
                        defaults={'name': name.strip()}
                    )
                    st.session_state.candidate = candidate
                    st.session_state.candidate_name = candidate.name
                    st.session_state.candidate_email = candidate.email
                    go_to('dashboard')
                    st.rerun()
        st.caption("No account needed — just enter your name and email to get started.")

    st.divider()
    cols = st.columns(4)
    for col, (title, desc) in zip(cols, [
        ("📖 Reading", "Comprehension, fill-in-gaps, true/false"),
        ("✍️ Writing", "Short answers, essays, gap-fill"),
        ("🎤 Speaking", "Read aloud, describe, give opinions"),
        ("🎧 Listening", "AI-generated audio, comprehension"),
    ]):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)
    st.info("**Flow:** A1 → C2. Each level tests all 4 skills. Score ≥80% to unlock the next level.")


def page_dashboard():
    """Candidate dashboard — mirrors the Lovable app layout."""
    candidate = st.session_state.candidate
    if not candidate:
        go_to('home')
        st.rerun()
        return

    try:
        candidate.refresh_from_db()
    except Exception:
        pass

    st.markdown(f"## 👤 {candidate.name}'s Dashboard")
    st.divider()

    # ── Stats cards ──────────────────────────────────────────────────
    completed_sessions = AssessmentSession.objects.filter(candidate=candidate, is_completed=True)
    total_sessions = completed_sessions.count()
    avg_score = 0.0
    if total_sessions > 0:
        avg_score = sum(s.percentage for s in completed_sessions) / total_sessions

    skill_avgs = {}
    for ss in SkillScore.objects.filter(session__candidate=candidate).select_related('skill'):
        skill_avgs.setdefault(ss.skill.code, []).append(ss.percentage)
    strongest_skill = (
        max(skill_avgs, key=lambda k: sum(skill_avgs[k]) / len(skill_avgs[k]))
        if skill_avgs else None
    )

    current_level_obj = candidate.current_cefr_level
    current_level_code = current_level_obj.code if current_level_obj else 'N/A'
    current_sublevel_obj = candidate.current_sublevel

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("ASSESSMENTS", total_sessions)
    with col2:
        st.metric("AVERAGE SCORE", f"{avg_score:.0f}%" if total_sessions > 0 else "—")
    with col3:
        if strongest_skill:
            icon = SKILL_ICONS.get(strongest_skill, '')
            st.metric("STRONGEST SKILL", f"{icon} {strongest_skill.title()}")
        else:
            st.metric("STRONGEST SKILL", "—")
    with col4:
        sub_suffix = f" / {current_sublevel_obj.code}" if current_sublevel_obj else ""
        st.metric("CURRENT LEVEL", f"{current_level_code}{sub_suffix}")

    # ── CEFR Progression ─────────────────────────────────────────────
    st.divider()
    st.markdown("### CEFR Progression")

    levels = list(CEFRLevel.objects.all().order_by('order'))
    passed_level_codes = set()
    if current_level_obj:
        for lv in levels:
            if lv.order < current_level_obj.order:
                passed_level_codes.add(lv.code)

    level_cols = st.columns(len(levels))
    for col, lv in zip(level_cols, levels):
        with col:
            is_passed = lv.code in passed_level_codes
            is_current = current_level_obj and lv.code == current_level_obj.code
            if is_passed:
                bg, fg, icon = '#22C55E', 'white', '✅'
            elif is_current:
                bg, fg, icon = '#3B82F6', 'white', '📍'
            else:
                bg, fg, icon = '#E5E7EB', '#9CA3AF', '🔒'
            st.markdown(
                f'<div style="background:{bg};color:{fg};border-radius:12px;padding:14px 8px;'
                f'text-align:center;margin:2px;">'
                f'<div style="font-size:20px">{icon}</div>'
                f'<div style="font-weight:700;font-size:17px;margin-top:4px">{lv.code}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    st.caption("≥80% to unlock the next level")

    # ── Sub-Level Progression ─────────────────────────────────────────
    from assessment.models import CEFRSubLevel
    if current_level_obj:
        sublevels = list(CEFRSubLevel.objects.filter(
            cefr_level=current_level_obj, is_active=True
        ).order_by('unit_order'))
        if sublevels:
            st.divider()
            st.markdown(f"### {current_level_code} Sub-Level Progression")
            row1 = sublevels[:6]
            row2 = sublevels[6:]
            for row in (row1, row2):
                if not row:
                    continue
                row_cols = st.columns(len(row))
                for col, sl in zip(row_cols, row):
                    with col:
                        is_current_sub = (
                            current_sublevel_obj and sl.code == current_sublevel_obj.code
                        )
                        is_past_sub = bool(
                            current_sublevel_obj
                            and sl.unit_order < current_sublevel_obj.unit_order
                        )
                        if is_past_sub:
                            bg, fg, sub_icon = '#22C55E', 'white', '✅'
                        elif is_current_sub:
                            bg, fg, sub_icon = '#3B82F6', 'white', '📍'
                        else:
                            bg, fg, sub_icon = '#E5E7EB', '#9CA3AF', '🔒'
                        st.markdown(
                            f'<div style="background:{bg};color:{fg};border-radius:8px;'
                            f'padding:8px 4px;text-align:center;margin:2px;">'
                            f'<div style="font-size:14px">{sub_icon}</div>'
                            f'<div style="font-weight:700;font-size:12px;margin-top:2px">{sl.code}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            st.caption("Complete each sub-level (≥80%) to progress to the next")

    # ── Quick actions ─────────────────────────────────────────────────
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 Start Assessment", type="primary", use_container_width=True):
            go_to('setup')
            st.rerun()
    with col2:
        if st.button("📋 Question Bank", use_container_width=True):
            go_to('questions')
            st.rerun()
    with col3:
        if st.button("📜 History", use_container_width=True):
            go_to('history')
            st.rerun()

    # ── Level Roadmap ─────────────────────────────────────────────────
    st.divider()
    st.markdown("### Level Roadmap")
    st.caption("Each level tests all 4 skills: Reading → Writing → Listening → Speaking")

    for lv in levels:
        is_passed = lv.code in passed_level_codes
        is_current = current_level_obj and lv.code == current_level_obj.code
        is_locked = not is_passed and not is_current
        prefix = '✅ ' if is_passed else '📍 ' if is_current else '🔒 '
        with st.expander(f"{prefix}{lv.code} — {lv.name}", expanded=bool(is_current)):
            if lv.description:
                st.caption(lv.description)
            skill_cols = st.columns(4)
            for sc, (sk_code, sk_icon) in zip(skill_cols, SKILL_ICONS.items()):
                with sc:
                    q_cnt = Question.objects.filter(
                        cefr_level=lv, skill__code=sk_code, is_active=True
                    ).count()
                    st.metric(f"{sk_icon} {sk_code.title()}", q_cnt)
            if is_current:
                st.success("Current unlocked level. Use 'Start / Continue Assessment' above.")
            elif is_passed:
                st.caption("Completed")
            else:
                st.caption("Locked until previous level/sublevel is passed")

    # ── Recent sessions ───────────────────────────────────────────────
    if total_sessions > 0:
        st.divider()
        st.markdown("### Recent Sessions")
        recent = (
            completed_sessions
            .select_related('starting_level', 'final_level')
            .order_by('-started_at')[:5]
        )
        for s in recent:
            mark = "✅" if s.percentage >= 80 else "❌"
            lv_code = s.final_level.code if s.final_level else '?'
            date_str = s.started_at.strftime('%b %d, %Y') if s.started_at else ''
            st.markdown(f"{mark} Level **{lv_code}** — **{s.percentage:.0f}%** — {date_str}")


def page_setup():
    """Locked assessment setup: candidate info + progression overview."""
    st.markdown("## 🎯 Start Your Assessment")

    from assessment.models import DifficultyTier, CEFRSubLevel

    candidate = st.session_state.candidate
    current_tier_code = 'beginner'
    current_level_code = 'A1'
    current_sublevel_code = 'A1.1'

    if candidate:
        try:
            candidate.refresh_from_db()
        except Exception:
            pass
        if candidate.current_difficulty_tier:
            current_tier_code = candidate.current_difficulty_tier.code
        if candidate.current_cefr_level:
            current_level_code = candidate.current_cefr_level.code
        if candidate.current_sublevel:
            current_sublevel_code = candidate.current_sublevel.code
        else:
            sl = CEFRSubLevel.objects.filter(cefr_level__code=current_level_code, is_active=True).order_by('unit_order').first()
            if sl:
                current_sublevel_code = sl.code

    st.markdown("### Difficulty Tiers")
    tiers = list(DifficultyTier.objects.all().order_by('order'))
    if tiers:
        tier_cols = st.columns(len(tiers))
        current_order = next((t.order for t in tiers if t.code == current_tier_code), 1)
        for col, tier in zip(tier_cols, tiers):
            with col:
                is_current = tier.code == current_tier_code
                is_unlocked = tier.order <= current_order
                icon = '📍' if is_current else '✅' if is_unlocked else '🔒'
                bg = '#3B82F6' if is_current else '#22C55E' if is_unlocked else '#E5E7EB'
                fg = 'white' if is_current or is_unlocked else '#9CA3AF'
                st.markdown(
                    f'<div style="background:{bg};color:{fg};border-radius:12px;padding:12px 8px;text-align:center;">'
                    f'<div style="font-size:20px">{icon}</div>'
                    f'<div style="font-weight:700">{tier.name}</div>'
                    f'<div style="font-size:12px;opacity:0.9">{tier.code}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.info(
        f"Current path: **{current_tier_code.title()}** → **{current_level_code}** → "
        f"**{current_sublevel_code}** → **Reading**"
    )
    st.caption("Progression is automatic: A1.1 → A1.2 → A1.3 → ... → C2.3, then next tier unlocks.")

    with st.form("setup_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your Name", value=st.session_state.candidate_name or "")
        with col2:
            email = st.text_input("Your Email", value=st.session_state.candidate_email or "")

        st.divider()
        st.markdown("**Flow:** Reading → Writing → Listening → Speaking (5 questions each skill, 80% to pass)")
        q_count = Question.objects.filter(
            difficulty_tier__code=current_tier_code,
            cefr_level__code=current_level_code,
            sublevel__code=current_sublevel_code,
            is_active=True,
        ).count()
        st.caption(f"Questions available for this selection: {q_count}")

        submitted = st.form_submit_button("Begin Assessment", type="primary", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("Please enter your name.")
            elif not email.strip():
                st.error("Please enter your email.")
            else:
                st.session_state.candidate_name = name.strip()
                st.session_state.candidate_email = email.strip()
                _start_assessment()
                st.rerun()

    if st.button("← Back"):
        go_to('dashboard' if st.session_state.candidate else 'home')
        st.rerun()


def _start_assessment():
    """Initialize the adaptive engine and start a session."""
    if st.session_state.candidate:
        candidate = st.session_state.candidate
    else:
        candidate, _ = Candidate.objects.get_or_create(
            email=st.session_state.candidate_email,
            defaults={'name': st.session_state.candidate_name}
        )
        st.session_state.candidate = candidate

    engine = AdaptiveEngine(
        candidate,
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
        # Always flush stale audio before fetching a new question
        st.session_state.tts_audio_b64 = None
        st.session_state.tts_text = None

        q = engine.get_next_question()
        if q is None:
            go_to('results')
            st.rerun()
            return
        st.session_state.current_question = q
        st.session_state.question_number += 1
        st.session_state.question_retry_pending = False
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
            st.success(f"✅ Correct! +{r['score']} points — {r['feedback']}")
        elif r.get('action') == 'QUESTION_RETRY':
            remaining = r.get('question_remaining_attempts', 1)
            st.error(f"❌ Incorrect — {r['feedback']}")
            st.warning(f"🔁 You have **{remaining}** more attempt — try the same question again!")
            # Keep feedback visible until next submit; don't clear yet
        else:
            st.error(f"❌ Incorrect — {r['feedback']}")
            st.session_state.last_result = None
    # Always clear non-retry results after display
    if st.session_state.last_result and st.session_state.last_result.get('action') != 'QUESTION_RETRY':
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

    elif fmt in ('text_input', 'sentence_build'):
        with st.form(f"text_{question.question_id}"):
            label = "Build your sentence:" if fmt == 'sentence_build' else "Your answer:"
            answer = st.text_input(label, key=f"text_input_{question.question_id}")
            submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)

            if submitted:
                if not answer.strip():
                    st.error("Please enter an answer.")
                else:
                    _submit_answer(question, response_text=answer.strip())
                    st.rerun()

    elif fmt in ('long_text', 'audio', 'picture_prompt'):
        with st.form(f"long_{question.question_id}"):
            label = "Describe what you see:" if fmt == 'picture_prompt' else "Your response:"
            answer = st.text_area(
                label,
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
            # Legacy fallback: some matching items are actually choice questions.
            options = list(question.options.all().order_by('order'))
            if options:
                with st.form(f"legacy_match_choice_{question.question_id}"):
                    choices = {f"{opt.label}. {opt.text}": opt.label for opt in options}
                    selected = st.radio(
                        "Select your answer:",
                        list(choices.keys()),
                        key=f"legacy_match_radio_{question.question_id}"
                    )
                    submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)
                    if submitted:
                        _submit_answer(question, selected_option_label=choices[selected])
                        st.rerun()
                return

            st.warning("No matching pairs available.")
            with st.form(f"legacy_match_text_{question.question_id}"):
                answer = st.text_input("Your answer:", key=f"legacy_match_text_input_{question.question_id}")
                submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)
                if submitted:
                    if not answer.strip():
                        st.error("Please enter an answer.")
                    else:
                        _submit_answer(question, response_text=answer.strip())
                        st.rerun()
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
        if not items:
            # Legacy fallback: some ordering items are stored as sequence text answers.
            st.info("Enter the correct sequence (example: B A C D).")
            with st.form(f"legacy_order_text_{question.question_id}"):
                answer = st.text_input("Your sequence:", key=f"legacy_order_text_input_{question.question_id}")
                submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)
                if submitted:
                    if not answer.strip():
                        st.error("Please enter the sequence.")
                    else:
                        _submit_answer(question, response_text=answer.strip())
                        st.rerun()
            return

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
        # Safety net: if new formats are seeded, keep the assessment usable.
        st.warning(f"Unknown response format '{fmt}'. Using text response fallback.")
        with st.form(f"fallback_{question.question_id}"):
            answer = st.text_area(
                "Your response:",
                height=140,
                key=f"fallback_input_{question.question_id}",
                placeholder="Type your answer here..."
            )
            submitted = st.form_submit_button("Submit Answer", type="primary", use_container_width=True)
            if submitted:
                if not answer.strip():
                    st.error("Please enter a response.")
                else:
                    _submit_answer(question, response_text=answer.strip())
                    st.rerun()


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
    st.session_state.tts_audio_b64 = None

    action = result.get('action', 'CONTINUE')

    if action == 'QUESTION_RETRY':
        # Wrong on first attempt — keep the same question loaded, just refresh feedback
        st.session_state.question_retry_pending = True
        # Do NOT clear current_question so the same question re-renders
    else:
        st.session_state.current_question = None
        st.session_state.question_retry_pending = False

    # Check for skill transition
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
            next_dest = final['next_level']
            if st.button(f"🚀 Try {next_dest}", type="primary", use_container_width=True):
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

        # Candidate info + logout
        candidate = st.session_state.candidate
        if candidate:
            st.markdown(f"**👤 {candidate.name}**")
            current_lv = candidate.current_cefr_level.code if candidate.current_cefr_level else 'A1'
            st.caption(f"Level: {current_lv} | {candidate.email}")
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.candidate = None
                st.session_state.engine = None
                st.session_state.current_question = None
                go_to('home')
                st.rerun()
            st.divider()
            if st.button("🏠 Dashboard", use_container_width=True):
                go_to('dashboard')
                st.rerun()
        else:
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
    elif page == 'dashboard':
        page_dashboard()
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
