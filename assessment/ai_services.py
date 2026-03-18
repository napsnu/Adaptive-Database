"""
AI Services for the CEFR English Learning Platform.

- TTS: Text-to-Speech via HuggingFace Inference API (Kokoro-82M)
- Gemini: AI-powered grading for speaking & listening responses
"""

import base64
import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


# ── TTS Service ──────────────────────────────────────────────────────

def generate_tts_audio(text, speed=1.0):
    """
    Generate speech audio from text using HuggingFace Kokoro-82M TTS model.
    Args:
        text: The text to convert to speech.
        speed: Speech rate (0.5 = slow for beginners, 1.0 = normal, etc.)
    Returns base64-encoded audio bytes, or None on failure.
    """
    api_key = settings.HUGGINGFACE_API_KEY
    if not api_key:
        logger.warning('HUGGINGFACE_API_KEY not set — TTS unavailable')
        return None

    # Remove [Transcript] and [Audio...] prefixes from text
    text = re.sub(r'^\[Transcript\]\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\[Audio[^\]]*\]\s*', '', text, flags=re.IGNORECASE)

    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(
            provider="replicate",
            api_key=api_key,
        )
        # Generate with optional speed parameter (Kokoro supports speed control via params)
        audio_bytes = client.text_to_speech(
            text,
            model="hexgrad/Kokoro-82M",
        )
        # Note: If Kokoro supports speed in future API updates, add: speed=speed
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f'TTS generation failed: {e}')
        return None


# ── Gemini AI Grading Service ────────────────────────────────────────

def grade_with_gemini(question_text, response_text, skill_code, question_type_code,
                      cefr_level, max_score, expected_text=None):
    """
    Use Google Gemini API to grade a speaking or listening response.

    Returns: (is_correct: bool, score: float, feedback: str)
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.warning('GEMINI_API_KEY not set — falling back to basic grading')
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = _build_grading_prompt(
            question_text, response_text, skill_code,
            question_type_code, cefr_level, max_score, expected_text
        )

        response = model.generate_content(prompt)
        return _parse_gemini_response(response.text, max_score)

    except Exception as e:
        logger.error(f'Gemini grading failed: {e}')
        return None


def _build_grading_prompt(question_text, response_text, skill_code,
                          question_type_code, cefr_level, max_score, expected_text):
    """Build the grading prompt for Gemini."""

    if skill_code == 'speaking':
        if question_type_code == 'read_aloud':
            return f"""You are a CEFR English examiner grading a READ ALOUD speaking task at level {cefr_level}.

The candidate was asked to read this passage aloud:
"{expected_text or question_text}"

Their speech was transcribed as:
"{response_text}"

Grade this on a scale of 0 to {max_score} points considering:
- Accuracy: How closely does the transcription match the original text?
- Completeness: Did they read the full passage?
- Pronunciation indicators: Any words clearly mispronounced (shown by transcription errors)?

For CEFR {cefr_level} level, be appropriately lenient/strict.

Respond in EXACTLY this JSON format (no markdown, no extra text):
{{"score": <number 0-{max_score}>, "is_correct": <true if score >= {max_score * 0.6}>, "feedback": "<2-3 sentence feedback with specific suggestions>"}}"""

        else:  # describe_picture, opinion_essay
            return f"""You are a CEFR English examiner grading a SPEAKING task at level {cefr_level}.
Task type: {question_type_code}

Question: "{question_text}"

The candidate's spoken response (transcribed):
"{response_text}"

Grade this on a scale of 0 to {max_score} points using CEFR {cefr_level} criteria:
- Content & Relevance: Does the response address the question?
- Vocabulary: Appropriate range for {cefr_level} level?
- Grammar: Accuracy appropriate for {cefr_level}?
- Fluency & Coherence: Is the response well-organized?
- Length: Is it sufficient for a {cefr_level} response?

Respond in EXACTLY this JSON format (no markdown, no extra text):
{{"score": <number 0-{max_score}>, "is_correct": <true if score >= {max_score * 0.6}>, "feedback": "<2-3 sentence feedback with specific praise and suggestions>"}}"""

    elif skill_code == 'listening':
        return f"""You are a CEFR English examiner grading a LISTENING comprehension response at level {cefr_level}.

The audio passage was: "{expected_text or question_text}"
The question asked: "{question_text}"
The candidate's answer: "{response_text}"

Grade this on a scale of 0 to {max_score} points:
- Comprehension: Did the candidate understand the audio content?
- Accuracy: Is their answer correct based on what was said?
- Completeness: Did they capture the key information?

Respond in EXACTLY this JSON format (no markdown, no extra text):
{{"score": <number 0-{max_score}>, "is_correct": <true if score >= {max_score * 0.6}>, "feedback": "<2-3 sentence feedback>"}}"""

    else:
        return f"""You are a CEFR English examiner grading a {skill_code} response at level {cefr_level}.

Question: "{question_text}"
Response: "{response_text}"

Grade on a scale of 0 to {max_score}. Respond in EXACTLY this JSON format:
{{"score": <number 0-{max_score}>, "is_correct": <true if score >= {max_score * 0.6}>, "feedback": "<feedback>"}}"""


def _parse_gemini_response(response_text, max_score):
    """Parse JSON response from Gemini. Returns (is_correct, score, feedback) or None."""
    try:
        # Strip any markdown code block markers
        cleaned = response_text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        score = float(data.get('score', 0))
        score = max(0.0, min(float(max_score), score))
        is_correct = bool(data.get('is_correct', score >= max_score * 0.6))
        feedback = str(data.get('feedback', 'Graded by AI'))
        return is_correct, round(score, 2), feedback
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f'Failed to parse Gemini response: {e} | Raw: {response_text[:200]}')
        return None
