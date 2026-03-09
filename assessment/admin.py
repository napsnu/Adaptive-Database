from django.contrib import admin
from .models import (
    CEFRLevel, Skill, QuestionType, Topic,
    Question, QuestionOption, MatchingPair, OrderingItem,
    Candidate, AssessmentSession, Response,
    SkillScore, LevelProgress,
)


# ── Inlines ──────────────────────────────────────────────────────────

class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


class MatchingPairInline(admin.TabularInline):
    model = MatchingPair
    extra = 0


class OrderingItemInline(admin.TabularInline):
    model = OrderingItem
    extra = 0


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0
    readonly_fields = ('candidate', 'question', 'is_correct', 'score', 'responded_at')
    can_delete = False


class SkillScoreInline(admin.TabularInline):
    model = SkillScore
    extra = 0
    readonly_fields = ('skill', 'total_questions', 'correct_answers', 'percentage')


# ── Model Admins ─────────────────────────────────────────────────────

@admin.register(CEFRLevel)
class CEFRLevelAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'order', 'min_score', 'max_score')
    ordering = ('order',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'order')
    ordering = ('order',)


@admin.register(QuestionType)
class QuestionTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'response_format', 'is_auto_gradable')
    list_filter = ('is_auto_gradable', 'response_format')
    filter_horizontal = ('skills',)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    filter_horizontal = ('cefr_levels',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_id', 'title', 'cefr_level', 'skill', 'question_type', 'topic', 'difficulty', 'is_active')
    list_filter = ('cefr_level', 'skill', 'question_type', 'topic', 'difficulty', 'is_active')
    search_fields = ('question_id', 'title', 'question_text')
    inlines = [QuestionOptionInline, MatchingPairInline, OrderingItemInline]


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ('question', 'label', 'text', 'is_correct')
    list_filter = ('is_correct',)


@admin.register(MatchingPair)
class MatchingPairAdmin(admin.ModelAdmin):
    list_display = ('question', 'left_text', 'right_text')


@admin.register(OrderingItem)
class OrderingItemAdmin(admin.ModelAdmin):
    list_display = ('question', 'text', 'correct_position')


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'current_cefr_level', 'created_at')
    search_fields = ('name', 'email')


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'session_type', 'skill_focus',
                    'starting_level', 'final_level', 'total_questions',
                    'correct_answers', 'is_completed', 'started_at')
    list_filter = ('session_type', 'is_completed', 'skill_focus')
    inlines = [ResponseInline, SkillScoreInline]


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'question', 'is_correct', 'score', 'max_score', 'responded_at')
    list_filter = ('is_correct',)


@admin.register(SkillScore)
class SkillScoreAdmin(admin.ModelAdmin):
    list_display = ('session', 'skill', 'total_questions', 'correct_answers', 'percentage', 'cefr_level_achieved')


@admin.register(LevelProgress)
class LevelProgressAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'cefr_level', 'skill', 'is_unlocked', 'completion_percentage', 'best_score', 'attempts')
    list_filter = ('cefr_level', 'skill', 'is_unlocked')
