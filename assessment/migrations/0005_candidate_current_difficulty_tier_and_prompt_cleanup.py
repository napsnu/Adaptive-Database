from django.db import migrations, models
import django.db.models.deletion
import re


def _forward(apps, schema_editor):
    Candidate = apps.get_model('assessment', 'Candidate')
    CEFRLevel = apps.get_model('assessment', 'CEFRLevel')
    CEFRSubLevel = apps.get_model('assessment', 'CEFRSubLevel')
    DifficultyTier = apps.get_model('assessment', 'DifficultyTier')
    Question = apps.get_model('assessment', 'Question')

    beginner = DifficultyTier.objects.filter(code='beginner').first() or DifficultyTier.objects.order_by('order').first()
    a1 = CEFRLevel.objects.filter(code='A1').first() or CEFRLevel.objects.order_by('order').first()
    a1_first = None
    if a1:
        a1_first = CEFRSubLevel.objects.filter(cefr_level=a1, is_active=True).order_by('unit_order').first()

    # Initialize candidate progression defaults where missing.
    for candidate in Candidate.objects.all():
        dirty = False
        if getattr(candidate, 'current_difficulty_tier_id', None) is None and beginner:
            candidate.current_difficulty_tier = beginner
            dirty = True
        if candidate.current_cefr_level_id is None and a1:
            candidate.current_cefr_level = a1
            dirty = True
        if candidate.current_sublevel_id is None and a1_first:
            candidate.current_sublevel = a1_first
            dirty = True
        if dirty:
            candidate.save()

    # Remove duplicated writing prompt artifact from existing questions.
    pattern = re.compile(r"\s*Keep ideas coherent and relevant to [^.]+\.\s*", flags=re.IGNORECASE)
    for question in Question.objects.all().only('id', 'question_text'):
        text = question.question_text or ''
        cleaned = pattern.sub(' ', text)
        cleaned = re.sub(r"\s{2,}", ' ', cleaned).strip()
        if cleaned != text:
            question.question_text = cleaned
            question.save(update_fields=['question_text'])


def _backward(apps, schema_editor):
    # Prompt cleanup and candidate tier defaults are intentionally non-reversible.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0004_difficulty_tier_accepted_answers_question_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='current_difficulty_tier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='candidates', to='assessment.difficultytier'),
        ),
        migrations.RunPython(_forward, _backward),
    ]
