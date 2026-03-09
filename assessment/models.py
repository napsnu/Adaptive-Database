"""
Database models for the Adaptive CEFR English Learning Platform.

Covers all 4 language skills (Reading, Writing, Speaking, Listening) with
multiple question types per skill and topics that vary by CEFR level.

Models:
 1. CEFRLevel       - A1 through C2 with score thresholds
 2. Skill           - Reading, Writing, Speaking, Listening
 3. QuestionType    - MCQ, fill-in-gaps, matching, describe picture, write letter, etc.
 4. Topic           - Greetings, Travel, Business, etc. (linked to levels)
 5. Question        - A single question linking level + skill + type + topic
 6. QuestionOption  - Answer choices for MCQ / True-False questions
 7. MatchingPair    - Left-Right pairs for matching questions
 8. OrderingItem    - Items with correct positions for ordering questions
 9. Candidate       - A learner / student
10. AssessmentSession - A test or practice session (adaptive or fixed)
11. Response        - A candidate's answer to one question
12. SkillScore      - Aggregated score per skill within a session
13. LevelProgress   - Long-term progress tracker per candidate x skill x level
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


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
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='questions')
    question_type = models.ForeignKey(QuestionType, on_delete=models.CASCADE, related_name='questions')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')

    title = models.CharField(max_length=200)
    instruction_text = models.TextField(blank=True, help_text="Instructions for the learner")
    content_text = models.TextField(blank=True, help_text="Reading passage, listening script, scenario")
    question_text = models.TextField(help_text="The actual question or prompt")

    media_url = models.URLField(max_length=500, blank=True, help_text="Image / audio / video URL")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, blank=True, default='')

    correct_answer = models.TextField(blank=True, help_text="Correct answer for auto-gradable types")
    sample_answer = models.TextField(blank=True, help_text="Model answer for subjective types")
    explanation = models.TextField(blank=True, help_text="Why the correct answer is correct")

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
# 9. CANDIDATES
# =====================================================================

class Candidate(models.Model):
    """A learner / student using the platform."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    native_language = models.CharField(max_length=100, blank=True)
    current_cefr_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
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
# 10. ASSESSMENT SESSIONS
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
    current_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_current'
    )
    final_level = models.ForeignKey(
        CEFRLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_final'
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
# 11. RESPONSES
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
# 12. SKILL SCORES (aggregated per session)
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
