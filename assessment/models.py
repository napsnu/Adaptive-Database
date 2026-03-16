"""
Database models for the Adaptive CEFR English Learning Platform.

Covers all 4 language skills (Reading, Writing, Speaking, Listening) with
multiple question types per skill and topics that vary by CEFR level.

Models:
 0. DifficultyTier  - Beginner / Intermediate / Advanced (grade-band grouping)
 1. CEFRLevel       - A1 through C2 with score thresholds
 2. CEFRSubLevel    - Unit-level path inside a CEFR level (e.g., A1.1, A1.2, A1.3)
 3. Skill           - Reading, Writing, Speaking, Listening
 4. QuestionType    - MCQ, fill-in-gaps, matching, describe picture, write letter, etc.
 5. Topic           - Greetings, Travel, Business, etc. (linked to levels)
 6. Question        - A single question linking tier + level + sublevel + skill + type + topic
 7. AnswerSample    - Multiple acceptable answers for subjective questions
 8. QuestionOption  - Answer choices for MCQ / True-False questions
 9. MatchingPair    - Left-Right pairs for matching questions
10. OrderingItem    - Items with correct positions for ordering questions
11. Candidate       - A learner / student
12. AssessmentSession - A test or practice session (adaptive or fixed)
13. Response        - A candidate's answer to one question
14. SkillScore      - Aggregated score per skill within a session
15. UserAttempt     - Per-question attempt log for analytics
16. UserProgress    - Long-term candidate progress per sublevel x skill
17. LevelProgress   - Legacy progress tracker per candidate x skill x level
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


# =====================================================================
# 0. DIFFICULTY TIERS  (Beginner → Intermediate → Advanced)
# =====================================================================

class DifficultyTier(models.Model):
    """Grade-band grouping: Beginner (Gr 4-5), Intermediate (Gr 6-7), Advanced (Gr 8-9+)."""

    TIER_CHOICES = [
        ('beginner',     'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced',     'Advanced'),
    ]

    code       = models.CharField(max_length=20, unique=True, choices=TIER_CHOICES)
    name       = models.CharField(max_length=50)
    order      = models.PositiveIntegerField(unique=True, help_text="1=Beginner, 2=Intermediate, 3=Advanced")
    grade_band = models.CharField(max_length=20, blank=True, help_text="e.g. '4-5', '6-7', '8-9'")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['order']
        verbose_name = "Difficulty Tier"
        verbose_name_plural = "Difficulty Tiers"

    def __str__(self):
        return self.name


# =====================================================================
# 1. CEFR LEVELS
# =====================================================================

class CEFRLevel(models.Model):
    """The 6 CEFR proficiency levels: A1, A2, B1, B2, C1, C2."""

    code = models.CharField(max_length=5, unique=True, help_text="e.g. A1, A2, B1")
    name = models.CharField(max_length=100, help_text="e.g. Breakthrough, Waystage")
    order = models.PositiveIntegerField(unique=True, help_text="1=A1 through 6=C2")
    description = models.TextField(blank=True, help_text="General can-do summary")

    min_score = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
        help_text="Minimum composite score for this level (0-10)"
    )
    max_score = models.FloatField(
        default=10.0, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
        help_text="Maximum composite score for this level (0-10)"
    )

    class Meta:
        ordering = ['order']
        verbose_name = "CEFR Level"
        verbose_name_plural = "CEFR Levels"

    def __str__(self):
        return f"{self.code} - {self.name}"


# =====================================================================
# 2. CEFR SUBLEVELS (UNITS)
# =====================================================================

class CEFRSubLevel(models.Model):
    """Unit-level progression inside one CEFR level, e.g. A1.1, A1.2."""

    cefr_level = models.ForeignKey(CEFRLevel, on_delete=models.CASCADE, related_name='sublevels')
    code = models.CharField(max_length=10, unique=True, help_text="e.g. A1.1, A2.5")
    unit_order = models.PositiveIntegerField(help_text="Unit number within level")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['cefr_level__order', 'unit_order']
        unique_together = ['cefr_level', 'unit_order']
        verbose_name = "CEFR Sublevel"
        verbose_name_plural = "CEFR Sublevels"

    def __str__(self):
        return self.code


# =====================================================================
# 2. SKILLS
# =====================================================================

class Skill(models.Model):
    """The 4 language skills: Reading, Writing, Speaking, Listening."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = "Skill"
        verbose_name_plural = "Skills"

    def __str__(self):
        return self.name


# =====================================================================
# 3. QUESTION TYPES
# =====================================================================

class QuestionType(models.Model):
    """Types of questions: multiple choice, fill in gaps, matching, etc."""

    RESPONSE_FORMAT_CHOICES = [
        ('single_choice', 'Single Choice (MCQ)'),
        ('true_false', 'True / False'),
        ('text_input', 'Short Text Input'),
        ('long_text', 'Long Text (Essay / Letter)'),
        ('audio', 'Audio Recording'),
        ('ordering', 'Ordering / Sequencing'),
        ('matching', 'Matching Pairs'),
        # Extended formats added for full skill-mode taxonomy
        ('dictation', 'Dictation'),
        ('sentence_build', 'Sentence Building'),
        ('error_correction', 'Error Correction'),
        ('picture_prompt', 'Picture-Based Prompt'),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    instruction_template = models.TextField(
        blank=True, help_text="Default instruction shown to learner"
    )
    is_auto_gradable = models.BooleanField(
        default=True, help_text="Can the system grade this automatically?"
    )
    response_format = models.CharField(
        max_length=20, choices=RESPONSE_FORMAT_CHOICES, default='single_choice'
    )
    skills = models.ManyToManyField(Skill, related_name='question_types', blank=True)

    class Meta:
        ordering = ['code']
        verbose_name = "Question Type"
        verbose_name_plural = "Question Types"

    def __str__(self):
        return self.name


# =====================================================================
# 4. TOPICS
# =====================================================================

class Topic(models.Model):
    """Topics that vary by CEFR level: Greetings, Travel, Business, etc."""

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    suggested_unit_order = models.PositiveIntegerField(null=True, blank=True)
    cefr_levels = models.ManyToManyField(CEFRLevel, related_name='topics', blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Topic"
        verbose_name_plural = "Topics"

    def __str__(self):
        return self.name


# =====================================================================
# 5. QUESTIONS
# =====================================================================

class Question(models.Model):
    """A single question in the learning platform."""

    MEDIA_TYPE_CHOICES = [
        ('', 'None'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('video', 'Video'),
    ]

    question_id = models.CharField(max_length=30, unique=True, help_text="e.g. A1-READ-MCQ-001")
    cefr_level = models.ForeignKey(CEFRLevel, on_delete=models.CASCADE, related_name='questions')
    sublevel = models.ForeignKey(
        CEFRSubLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='questions',
        help_text="Unit-based CEFR sublevel (e.g., A1.3)",
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='questions')
    question_type = models.ForeignKey(QuestionType, on_delete=models.CASCADE, related_name='questions')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')

    title = models.CharField(max_length=200)
    instruction_text = models.TextField(blank=True, help_text="Instructions for the learner")
    content_text = models.TextField(blank=True, help_text="Reading passage, listening script, scenario")
    question_text = models.TextField(help_text="The actual question or prompt")

    media_url = models.URLField(max_length=500, blank=True, help_text="Image / audio / video URL")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, blank=True, default='')

    # ── Answer fields ─────────────────────────────────────────────────
    correct_answer = models.TextField(blank=True, help_text="Correct answer for objective (auto-gradable) types")
    accepted_answers = models.JSONField(
        default=list, blank=True,
        help_text="List of accepted answer strings for subjective types (used instead of AnswerSample for text matching)"
    )
    sample_answer = models.TextField(blank=True, help_text="Legacy: pipe-separated model answers for subjective types")
    explanation = models.TextField(blank=True, help_text="Why the correct answer is correct (shown after attempt)")

    # ── Answer-matching configuration ─────────────────────────────────
    MATCHING_MODE_CHOICES = [
        ('exact',         'Exact Match'),
        ('normalized',    'Normalised (strip + lowercase)'),
        ('keyword',       'Keyword Overlap'),
        ('multi_accepted', 'Multiple Accepted Answers'),
        ('ai_graded',     'AI Graded'),
    ]
    answer_matching_mode = models.CharField(
        max_length=20, choices=MATCHING_MODE_CHOICES, default='normalized',
        help_text="How the engine should compare the learner's response to the correct answer"
    )
    is_case_sensitive = models.BooleanField(default=False)

    # ── Speaking-mode extra payload ───────────────────────────────────
    speaking_topic = models.TextField(
        blank=True,
        help_text="Explicit topic or prompt for speaking questions (always sent to frontend)"
    )

    # ── Difficulty & tier ─────────────────────────────────────────────
    difficulty_tier = models.ForeignKey(
        'DifficultyTier',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='questions',
        help_text="Beginner / Intermediate / Advanced grade band",
    )
    difficulty = models.PositiveIntegerField(default=1, help_text="1=easy, 2=medium, 3=hard within level")
    points = models.PositiveIntegerField(default=1)
    time_limit_seconds = models.PositiveIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cefr_level__order', 'skill__order', 'question_id']
        verbose_name = "Question"
        verbose_name_plural = "Questions"

    def __str__(self):
        return f"[{self.question_id}] {self.title}"


# =====================================================================
# 7. ANSWER SAMPLES (for writing semantic matching)
# =====================================================================

class AnswerSample(models.Model):
    """Multiple acceptable sample answers for writing questions."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answer_samples')
    text = models.TextField(help_text="One acceptable answer sample")
    keywords = models.JSONField(default=list, blank=True, help_text="Optional anchor keywords")
    weight = models.FloatField(default=1.0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Answer Sample"
        verbose_name_plural = "Answer Samples"

    def __str__(self):
        return f"Sample for {self.question.question_id}"


# =====================================================================
# 6. QUESTION OPTIONS (for MCQ / True-False)
# =====================================================================

class QuestionOption(models.Model):
    """Answer choices for MCQ and true/false questions."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    label = models.CharField(max_length=5, help_text="A, B, C, D")
    text = models.TextField()
    media_url = models.URLField(max_length=500, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = "Question Option"
        verbose_name_plural = "Question Options"

    def __str__(self):
        mark = " [correct]" if self.is_correct else ""
        return f"{self.label}. {self.text[:60]}{mark}"


# =====================================================================
# 7. MATCHING PAIRS
# =====================================================================

class MatchingPair(models.Model):
    """Left-Right pairs for matching-type questions."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='matching_pairs')
    left_text = models.TextField()
    right_text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = "Matching Pair"
        verbose_name_plural = "Matching Pairs"

    def __str__(self):
        return f"{self.left_text[:30]} <-> {self.right_text[:30]}"


# =====================================================================
# 8. ORDERING ITEMS
# =====================================================================

class OrderingItem(models.Model):
    """Items with correct positions for ordering/sequencing questions."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='ordering_items')
    text = models.TextField()
    correct_position = models.PositiveIntegerField()

    class Meta:
        ordering = ['correct_position']
        verbose_name = "Ordering Item"
        verbose_name_plural = "Ordering Items"

    def __str__(self):
        return f"#{self.correct_position}: {self.text[:50]}"


# =====================================================================
# 11. CANDIDATES
# =====================================================================

class Candidate(models.Model):
    """A learner / student using the platform."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    native_language = models.CharField(max_length=100, blank=True)
    current_cefr_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
    )
    current_sublevel = models.ForeignKey(
        CEFRSubLevel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='candidates',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"

    def __str__(self):
        level = self.current_cefr_level.code if self.current_cefr_level else "New"
        return f"{self.name} ({level})"


# =====================================================================
# 12. ASSESSMENT SESSIONS
# =====================================================================

class AssessmentSession(models.Model):
    """A test or practice session - can focus on one skill or be mixed."""

    SESSION_TYPE_CHOICES = [
        ('placement', 'Placement Test'),
        ('practice', 'Practice'),
        ('skill_test', 'Skill Test'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='sessions')
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='practice')
    skill_focus = models.ForeignKey(
        Skill, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions', help_text="NULL = mixed / all skills"
    )

    starting_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, related_name='sessions_started'
    )
    starting_sublevel = models.ForeignKey(
        CEFRSubLevel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_started',
    )
    current_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_current'
    )
    current_sublevel = models.ForeignKey(
        CEFRSubLevel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_current',
    )
    final_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_final'
    )
    final_sublevel = models.ForeignKey(
        CEFRSubLevel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_final',
    )

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_score = models.FloatField(default=0)
    max_possible_score = models.FloatField(default=0)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']
        verbose_name = "Assessment Session"
        verbose_name_plural = "Assessment Sessions"

    def __str__(self):
        status = "Done" if self.is_completed else "Active"
        skill = self.skill_focus.name if self.skill_focus else "Mixed"
        return f"{self.candidate.name} - {skill} ({status})"

    @property
    def percentage(self):
        if self.max_possible_score > 0:
            return round((self.total_score / self.max_possible_score) * 100, 1)
        return 0.0


# =====================================================================
# 13. RESPONSES
# =====================================================================

class Response(models.Model):
    """A candidate's answer to one question within a session."""

    session = models.ForeignKey(AssessmentSession, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='responses')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='responses')

    selected_option = models.ForeignKey(
        QuestionOption, on_delete=models.SET_NULL, null=True, blank=True, related_name='responses'
    )
    response_text = models.TextField(blank=True, help_text="Typed answer")
    response_data = models.JSONField(null=True, blank=True, help_text="Structured data for matching/ordering")
    audio_file_path = models.CharField(max_length=500, blank=True)

    is_correct = models.BooleanField(null=True, help_text="NULL = not yet graded")
    score = models.FloatField(default=0)
    max_score = models.FloatField(default=1)
    feedback = models.TextField(blank=True)

    responded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['responded_at']
        verbose_name = "Response"
        verbose_name_plural = "Responses"

    def __str__(self):
        return f"{self.candidate.name} -> {self.question.question_id}"


# =====================================================================
# 14. SKILL SCORES (aggregated per session)
# =====================================================================
# 15. USER ATTEMPTS
# =====================================================================

class UserAttempt(models.Model):
    """Per-question attempt log for analytics and adaptive history."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='user_attempts')
    session = models.ForeignKey(AssessmentSession, on_delete=models.CASCADE, related_name='user_attempts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='user_attempts')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='user_attempts')
    cefr_level = models.ForeignKey(CEFRLevel, on_delete=models.CASCADE, related_name='user_attempts')
    sublevel = models.ForeignKey(
        CEFRSubLevel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='user_attempts',
    )

    submitted_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    score = models.FloatField(default=0)
    max_score = models.FloatField(default=1)
    attempt_no = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "User Attempt"
        verbose_name_plural = "User Attempts"


# =====================================================================
# 16. USER PROGRESS
# =====================================================================

class UserProgress(models.Model):
    """Progress state for candidate per CEFR sublevel and skill."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='user_progress')
    cefr_level = models.ForeignKey(CEFRLevel, on_delete=models.CASCADE, related_name='user_progress')
    sublevel = models.ForeignKey(CEFRSubLevel, on_delete=models.CASCADE, related_name='user_progress')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='user_progress')

    questions_answered = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    mastery_score = models.FloatField(default=0)
    is_unlocked = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['candidate', 'sublevel', 'skill']
        ordering = ['candidate__name', 'cefr_level__order', 'sublevel__unit_order', 'skill__order']
        verbose_name = "User Progress"
        verbose_name_plural = "User Progress"


# =====================================================================
# 17. LEVEL PROGRESS (long-term tracking)
# =====================================================================
# =====================================================================

class SkillScore(models.Model):
    """Aggregated score for one skill within one session."""

    session = models.ForeignKey(AssessmentSession, on_delete=models.CASCADE, related_name='skill_scores')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='skill_scores')
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_score = models.FloatField(default=0)
    max_possible_score = models.FloatField(default=0)
    percentage = models.FloatField(default=0)
    cefr_level_achieved = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='skill_scores'
    )

    class Meta:
        unique_together = ['session', 'skill']
        verbose_name = "Skill Score"
        verbose_name_plural = "Skill Scores"

    def __str__(self):
        return f"{self.skill.name}: {self.percentage:.0f}%"


# =====================================================================
# 13. LEVEL PROGRESS (long-term tracking)
# =====================================================================

class LevelProgress(models.Model):
    """Tracks a candidate's progress for each skill at each CEFR level."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='progress')
    cefr_level = models.ForeignKey(CEFRLevel, on_delete=models.CASCADE, related_name='progress')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='progress')

    is_unlocked = models.BooleanField(default=False)
    completion_percentage = models.FloatField(default=0)
    best_score = models.FloatField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['candidate', 'cefr_level', 'skill']
        verbose_name = "Level Progress"
        verbose_name_plural = "Level Progress"

    def __str__(self):
        return (f"{self.candidate.name} - {self.cefr_level.code} "
                f"{self.skill.name}: {self.completion_percentage:.0f}%")
