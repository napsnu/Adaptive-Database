from django.core.management.base import BaseCommand
from django.utils.text import slugify

from assessment.models import (
    CEFRLevel,
    CEFRSubLevel,
    Skill,
    Topic,
    QuestionType,
    Question,
    QuestionOption,
    AnswerSample,
)


TOPICS_BY_LEVEL = {
    "A1": [
        "Greetings & Introductions",
        "Origins & Location",
        "People & Family",
        "Clothing",
        "Food & Dining",
        "Daily Routine",
        "Weather",
        "Health",
        "Directions & Housing",
        "Hobbies & Interests",
        "Accommodation",
        "Shopping",
    ],
    "A2": [
        "Workplace Evaluations",
        "Past Events",
        "Personal History",
        "Hospitality",
        "Travel & Vacations",
        "Nature",
        "Entertainment",
        "Fashion",
        "Basic Work Communication",
        "Medical Emergencies",
        "Business Networking",
        "Business Proposals",
        "Games",
    ],
    "B1": [
        "Aspirations",
        "Job Interviews",
        "Media",
        "Education",
        "Music & Nightlife",
        "Health & Lifestyle",
        "Relationships",
        "Dining Out",
        "Basic Negotiations",
        "Workplace Safety",
        "Etiquette",
    ],
    "B2": [
        "Professional Meetings",
        "Cultural Norms",
        "Personal Finance",
        "Work-Life Balance",
        "Career Path",
        "Productivity",
        "Literature",
        "Social Graces",
        "Leadership",
        "Conflict Resolution",
        "Politics",
    ],
    "C1": [
        "Team Building & Success",
        "Art & Architecture",
        "Societal Issues",
        "Environment & Sustainability",
        "Current Events",
        "Risk Management",
        "Education Systems",
        "Humor",
        "Communication Styles",
        "Quality of Life",
        "Ethics",
    ],
    "C2": [
        "Science & Technology",
        "Pop Culture",
        "Creativity",
        "Financial Planning",
        "Stress Management",
        "Research Techniques",
    ],
}


class Command(BaseCommand):
    help = "Seed CEFR topics, sublevels, and a balanced 1000+ question bank"

    QUESTIONS_PER_SKILL_PER_SUBLEVEL = 4

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding structured CEFR curriculum..."))

        self._ensure_levels()
        self._ensure_skills()
        self._ensure_question_types()

        generated = 0
        for level_code, topics in TOPICS_BY_LEVEL.items():
            level = CEFRLevel.objects.get(code=level_code)
            for unit_order, topic_name in enumerate(topics, start=1):
                topic = self._ensure_topic(level, topic_name, unit_order)
                sublevel = self._ensure_sublevel(level, topic_name, unit_order)
                generated += self._seed_questions_for_sublevel(level, sublevel, topic)

        total_questions = Question.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"Curriculum seed complete. Generated/updated: {generated} questions. Total active questions: {total_questions}."
        ))

    def _ensure_levels(self):
        levels = [
            ("A1", "Breakthrough", 1),
            ("A2", "Waystage", 2),
            ("B1", "Threshold", 3),
            ("B2", "Vantage", 4),
            ("C1", "Effective Operational Proficiency", 5),
            ("C2", "Mastery", 6),
        ]
        for code, name, order in levels:
            CEFRLevel.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "order": order,
                },
            )

    def _ensure_skills(self):
        skills = [
            ("reading", "Reading", 1),
            ("writing", "Writing", 2),
            ("listening", "Listening", 3),
            ("speaking", "Speaking", 4),
        ]
        for code, name, order in skills:
            Skill.objects.update_or_create(
                code=code,
                defaults={"name": name, "order": order},
            )

    def _ensure_question_types(self):
        qtypes = [
            ("multiple_choice", "Multiple Choice", "single_choice", True),
            ("true_false", "True / False", "true_false", True),
            ("short_answer", "Short Answer", "text_input", True),
            ("opinion_essay", "Opinion", "long_text", False),
        ]
        for code, name, fmt, auto in qtypes:
            QuestionType.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "response_format": fmt,
                    "is_auto_gradable": auto,
                },
            )

    def _ensure_topic(self, level, topic_name, unit_order):
        topic_code = f"{level.code.lower()}_{unit_order:02d}_{slugify(topic_name).replace('-', '_')}"
        topic, _ = Topic.objects.update_or_create(
            code=topic_code,
            defaults={
                "name": topic_name,
                "description": f"{level.code} unit {unit_order}: {topic_name}",
                "suggested_unit_order": unit_order,
            },
        )
        topic.cefr_levels.add(level)
        return topic

    def _ensure_sublevel(self, level, topic_name, unit_order):
        code = f"{level.code}.{unit_order}"
        sublevel, _ = CEFRSubLevel.objects.update_or_create(
            code=code,
            defaults={
                "cefr_level": level,
                "unit_order": unit_order,
                "title": topic_name,
                "description": f"{level.code} unit {unit_order} on {topic_name}",
                "is_active": True,
            },
        )
        return sublevel

    def _seed_questions_for_sublevel(self, level, sublevel, topic):
        created_or_updated = 0

        reading_skill = Skill.objects.get(code="reading")
        writing_skill = Skill.objects.get(code="writing")
        listening_skill = Skill.objects.get(code="listening")
        speaking_skill = Skill.objects.get(code="speaking")

        qtype_mcq = QuestionType.objects.get(code="multiple_choice")
        qtype_tf = QuestionType.objects.get(code="true_false")
        qtype_short = QuestionType.objects.get(code="short_answer")
        qtype_opinion = QuestionType.objects.get(code="opinion_essay")

        for idx in range(1, self.QUESTIONS_PER_SKILL_PER_SUBLEVEL + 1):
            reading_id = f"{level.code}-U{sublevel.unit_order:02d}-READ-{idx:02d}"
            question, _ = Question.objects.update_or_create(
                question_id=reading_id,
                defaults={
                    "cefr_level": level,
                    "sublevel": sublevel,
                    "skill": reading_skill,
                    "question_type": qtype_mcq,
                    "topic": topic,
                    "title": f"{sublevel.code} Reading {idx}",
                    "content_text": f"Short passage about {topic.name} at {sublevel.code}.",
                    "question_text": f"Which sentence best matches the passage theme about {topic.name}?",
                    "difficulty": min(3, max(1, level.order // 2 + 1)),
                    "points": 1,
                    "is_active": True,
                },
            )
            question.options.all().delete()
            QuestionOption.objects.bulk_create([
                QuestionOption(question=question, label="A", text=f"A core idea about {topic.name}", is_correct=True, order=1),
                QuestionOption(question=question, label="B", text="An unrelated idea", is_correct=False, order=2),
                QuestionOption(question=question, label="C", text="A contradictory idea", is_correct=False, order=3),
                QuestionOption(question=question, label="D", text="A random detail", is_correct=False, order=4),
            ])
            created_or_updated += 1

            writing_id = f"{level.code}-U{sublevel.unit_order:02d}-WRIT-{idx:02d}"
            question, _ = Question.objects.update_or_create(
                question_id=writing_id,
                defaults={
                    "cefr_level": level,
                    "sublevel": sublevel,
                    "skill": writing_skill,
                    "question_type": qtype_short,
                    "topic": topic,
                    "title": f"{sublevel.code} Writing {idx}",
                    "question_text": f"Write 2-4 sentences about {topic.name} in everyday context.",
                    "sample_answer": "I often talk about this topic with my friends.|This topic is important in my daily life.|I can explain this topic clearly with simple examples.|I use useful vocabulary when I discuss this topic.",
                    "difficulty": min(3, max(1, level.order // 2 + 1)),
                    "points": 2,
                    "is_active": True,
                },
            )
            question.answer_samples.all().delete()
            samples = [
                f"I often discuss {topic.name.lower()} in my daily routine.",
                f"{topic.name} helps me communicate in practical situations.",
                f"I can describe {topic.name.lower()} with clear examples.",
                f"Learning {topic.name.lower()} improves my confidence.",
            ]
            for s_idx, text in enumerate(samples, start=1):
                AnswerSample.objects.create(
                    question=question,
                    text=text,
                    keywords=[w for w in topic.name.lower().split() if w.isalpha()],
                    order=s_idx,
                )
            created_or_updated += 1

            listening_id = f"{level.code}-U{sublevel.unit_order:02d}-LIST-{idx:02d}"
            question, _ = Question.objects.update_or_create(
                question_id=listening_id,
                defaults={
                    "cefr_level": level,
                    "sublevel": sublevel,
                    "skill": listening_skill,
                    "question_type": qtype_tf,
                    "topic": topic,
                    "title": f"{sublevel.code} Listening {idx}",
                    "content_text": f"[Audio transcript] A short dialogue about {topic.name}.",
                    "question_text": f"The speaker is discussing {topic.name}.",
                    "difficulty": min(3, max(1, level.order // 2 + 1)),
                    "points": 1,
                    "is_active": True,
                },
            )
            question.options.all().delete()
            QuestionOption.objects.bulk_create([
                QuestionOption(question=question, label="A", text="True", is_correct=True, order=1),
                QuestionOption(question=question, label="B", text="False", is_correct=False, order=2),
            ])
            created_or_updated += 1

            speaking_id = f"{level.code}-U{sublevel.unit_order:02d}-SPEAK-{idx:02d}"
            Question.objects.update_or_create(
                question_id=speaking_id,
                defaults={
                    "cefr_level": level,
                    "sublevel": sublevel,
                    "skill": speaking_skill,
                    "question_type": qtype_opinion,
                    "topic": topic,
                    "title": f"{sublevel.code} Speaking {idx}",
                    "question_text": f"Speak for 30-60 seconds about your opinion on {topic.name}.",
                    "sample_answer": f"In my opinion, {topic.name.lower()} is useful because it helps in real communication.",
                    "difficulty": min(3, max(1, level.order // 2 + 1)),
                    "points": 2,
                    "is_active": True,
                },
            )
            created_or_updated += 1

        return created_or_updated
