"""
Seed the database with CEFR English Learning Platform data.

Seeds:
 - 6 CEFR Levels
 - 4 Skills (Reading, Writing, Speaking, Listening)
 - 10 Question Types
 - 20 Topics mapped to levels
 - 72 Questions (6 levels x 4 skills x 3 questions each) with options
"""

from django.core.management.base import BaseCommand
from assessment.models import (
    CEFRLevel, Skill, QuestionType, Topic,
    Question, QuestionOption, MatchingPair, OrderingItem,
)


class Command(BaseCommand):
    help = 'Seed the database with CEFR English Learning Platform data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Seeding CEFR English Learning Platform Database...'
        ))
        self._seed_levels()
        self._seed_skills()
        self._seed_question_types()
        self._seed_topics()
        self._seed_questions()
        self.stdout.write(self.style.SUCCESS('\nDatabase seeding complete!'))
        self._print_summary()

    # =================================================================
    # CEFR LEVELS
    # =================================================================
    def _seed_levels(self):
        self.stdout.write('  Seeding CEFR Levels...')
        levels = [
            ('A1', 'Breakthrough', 1, 0.0, 2.0,
             'Can understand and use familiar everyday expressions and very basic phrases. '
             'Can introduce themselves and ask/answer questions about personal details.'),
            ('A2', 'Waystage', 2, 2.0, 4.0,
             'Can understand frequently used expressions related to immediate relevance. '
             'Can communicate in simple, routine tasks on familiar topics.'),
            ('B1', 'Threshold', 3, 4.0, 5.5,
             'Can understand main points of clear standard input on familiar matters. '
             'Can deal with most travel situations and produce simple connected text.'),
            ('B2', 'Vantage', 4, 5.5, 7.0,
             'Can understand main ideas of complex text including technical discussions. '
             'Can interact with fluency and spontaneity with native speakers.'),
            ('C1', 'Effective Operational Proficiency', 5, 7.0, 8.5,
             'Can understand a wide range of demanding, longer texts. '
             'Can express ideas fluently, spontaneously, and precisely for professional use.'),
            ('C2', 'Mastery', 6, 8.5, 10.0,
             'Can understand virtually everything heard or read with ease. '
             'Can express spontaneously with precision, differentiating finer shades of meaning.'),
        ]
        for code, name, order, mn, mx, desc in levels:
            obj, created = CEFRLevel.objects.update_or_create(
                code=code, defaults={
                    'name': name, 'order': order, 'min_score': mn,
                    'max_score': mx, 'description': desc,
                })
            self.stdout.write(f'    {"Created" if created else "Updated"}: {obj}')

    # =================================================================
    # SKILLS
    # =================================================================
    def _seed_skills(self):
        self.stdout.write('  Seeding Skills...')
        skills = [
            ('reading', 'Reading', 'Understanding written texts', 1),
            ('writing', 'Writing', 'Producing written texts', 2),
            ('speaking', 'Speaking', 'Oral production and interaction', 3),
            ('listening', 'Listening', 'Understanding spoken language', 4),
        ]
        for code, name, desc, order in skills:
            obj, created = Skill.objects.update_or_create(
                code=code, defaults={'name': name, 'description': desc, 'order': order})
            self.stdout.write(f'    {"Created" if created else "Updated"}: {obj}')

    # =================================================================
    # QUESTION TYPES
    # =================================================================
    def _seed_question_types(self):
        self.stdout.write('  Seeding Question Types...')
        types = [
            ('multiple_choice', 'Multiple Choice', 'single_choice', True,
             'Choose the correct answer from the options.',
             ['reading', 'listening']),
            ('true_false', 'True / False', 'true_false', True,
             'Decide if the statement is true or false.',
             ['reading', 'listening']),
            ('fill_in_gaps', 'Fill in the Gaps', 'text_input', True,
             'Complete the sentence with the correct word or phrase.',
             ['reading', 'writing', 'listening']),
            ('matching', 'Matching', 'matching', True,
             'Match items from the left column with items from the right column.',
             ['reading', 'listening']),
            ('ordering', 'Ordering / Sequencing', 'ordering', True,
             'Put the items in the correct order.',
             ['reading']),
            ('short_answer', 'Short Answer', 'text_input', True,
             'Write a short answer to the question.',
             ['reading', 'writing', 'listening']),
            ('describe_picture', 'Describe a Picture', 'long_text', False,
             'Look at the picture and write a description.',
             ['writing', 'speaking']),
            ('write_letter', 'Write a Letter / Email', 'long_text', False,
             'Write a letter or email based on the given situation.',
             ['writing']),
            ('opinion_essay', 'Opinion / Essay', 'long_text', False,
             'Write your opinion on the given topic with reasons.',
             ['writing', 'speaking']),
            ('read_aloud', 'Read Aloud', 'audio', False,
             'Read the given text aloud clearly.',
             ['speaking']),
        ]
        for code, name, fmt, auto, instr, skill_codes in types:
            obj, created = QuestionType.objects.update_or_create(
                code=code, defaults={
                    'name': name, 'response_format': fmt,
                    'is_auto_gradable': auto, 'instruction_template': instr,
                })
            skills = Skill.objects.filter(code__in=skill_codes)
            obj.skills.set(skills)
            self.stdout.write(f'    {"Created" if created else "Updated"}: {obj}')

    # =================================================================
    # TOPICS
    # =================================================================
    def _seed_topics(self):
        self.stdout.write('  Seeding Topics...')
        topics = [
            ('greetings', 'Greetings & Introductions',
             'Basic greetings, self-introduction, meeting people', ['A1', 'A2']),
            ('family', 'Family & Friends',
             'Family members, relationships, describing people', ['A1', 'A2']),
            ('food', 'Food & Drink',
             'Meals, ordering food, cooking, restaurants', ['A1', 'A2', 'B1']),
            ('daily_life', 'Daily Life & Routines',
             'Daily activities, time, schedules', ['A1', 'A2']),
            ('shopping', 'Shopping & Money',
             'Buying things, prices, stores, online shopping', ['A2', 'B1']),
            ('travel', 'Travel & Transport',
             'Holidays, directions, booking, transport', ['A2', 'B1']),
            ('hobbies', 'Hobbies & Leisure',
             'Sports, entertainment, free time activities', ['A2', 'B1']),
            ('health', 'Health & Wellbeing',
             'Body, doctor visits, healthy lifestyle', ['A2', 'B1']),
            ('education', 'Education & Learning',
             'School, university, courses, studying', ['B1', 'B2']),
            ('work', 'Work & Careers',
             'Jobs, workplace, interviews, professions', ['B1', 'B2']),
            ('technology', 'Technology & Internet',
             'Computers, apps, social media, digital life', ['B1', 'B2']),
            ('environment', 'Environment & Nature',
             'Climate, pollution, wildlife, sustainability', ['B1', 'B2']),
            ('science', 'Science & Innovation',
             'Scientific discoveries, research, progress', ['B2', 'C1']),
            ('media', 'Media & Communication',
             'News, journalism, advertising, social media effects', ['B2', 'C1']),
            ('politics', 'Politics & Society',
             'Government, laws, civic engagement, social issues', ['B2', 'C1']),
            ('business', 'Business & Economics',
             'Business proposals, markets, finance, trade', ['C1', 'C2']),
            ('academic', 'Academic & Research',
             'Research methodology, academic writing, peer review', ['C1', 'C2']),
            ('philosophy', 'Philosophy & Ethics',
             'Moral dilemmas, philosophical concepts, critical thinking', ['C1', 'C2']),
            ('literature', 'Literature & Arts',
             'Literary analysis, art criticism, cultural heritage', ['C2']),
            ('global_issues', 'Global Issues & Diplomacy',
             'International relations, global challenges, policy', ['C2']),
        ]
        for code, name, desc, level_codes in topics:
            obj, created = Topic.objects.update_or_create(
                code=code, defaults={'name': name, 'description': desc})
            levels = CEFRLevel.objects.filter(code__in=level_codes)
            obj.cefr_levels.set(levels)
            self.stdout.write(f'    {"Created" if created else "Updated"}: {obj}')

    # =================================================================
    # QUESTIONS (72 total: 6 levels x 4 skills x 3 questions)
    # =================================================================
    def _seed_questions(self):
        self.stdout.write('  Seeding Questions...')
        all_questions = (
            self._a1_questions() + self._a2_questions() +
            self._b1_questions() + self._b2_questions() +
            self._c1_questions() + self._c2_questions()
        )
        for q_data in all_questions:
            level = CEFRLevel.objects.get(code=q_data['level'])
            skill = Skill.objects.get(code=q_data['skill'])
            qtype = QuestionType.objects.get(code=q_data['qtype'])
            topic = Topic.objects.get(code=q_data['topic'])

            question, created = Question.objects.update_or_create(
                question_id=q_data['qid'],
                defaults={
                    'cefr_level': level, 'skill': skill, 'question_type': qtype,
                    'topic': topic, 'title': q_data['title'],
                    'instruction_text': q_data.get('instruction', ''),
                    'content_text': q_data.get('content', ''),
                    'question_text': q_data['question'],
                    'correct_answer': q_data.get('correct_answer', ''),
                    'sample_answer': q_data.get('sample_answer', ''),
                    'explanation': q_data.get('explanation', ''),
                    'difficulty': q_data.get('difficulty', 1),
                    'points': q_data.get('points', 1),
                    'time_limit_seconds': q_data.get('time_limit', None),
                })

            # Create options (MCQ / True-False)
            if 'options' in q_data:
                question.options.all().delete()
                for i, opt in enumerate(q_data['options']):
                    QuestionOption.objects.create(
                        question=question, label=opt[0], text=opt[1],
                        is_correct=opt[2], order=i)

            # Create matching pairs
            if 'pairs' in q_data:
                question.matching_pairs.all().delete()
                for i, pair in enumerate(q_data['pairs']):
                    MatchingPair.objects.create(
                        question=question, left_text=pair[0],
                        right_text=pair[1], order=i)

            # Create ordering items
            if 'order_items' in q_data:
                question.ordering_items.all().delete()
                for pos, text in enumerate(q_data['order_items'], 1):
                    OrderingItem.objects.create(
                        question=question, text=text, correct_position=pos)

            status = 'Created' if created else 'Updated'
            self.stdout.write(f'    {status}: {question}')

    # =================================================================
    # A1 QUESTIONS
    # =================================================================
    def _a1_questions(self):
        return [
            # ── A1 READING ──
            {
                'qid': 'A1-READ-MCQ-001', 'level': 'A1', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'greetings',
                'title': 'Self-Introduction Passage',
                'content': (
                    'Hello! My name is Tom. I am 20 years old. I am from England. '
                    'I live in London. I am a student. I study English and History. '
                    'I like football and music.'
                ),
                'question': 'Where does Tom live?',
                'explanation': 'The passage says "I live in London."',
                'difficulty': 1, 'time_limit': 60,
                'options': [
                    ('A', 'Paris', False),
                    ('B', 'London', True),
                    ('C', 'New York', False),
                    ('D', 'Bangkok', False),
                ],
            },
            {
                'qid': 'A1-READ-TF-001', 'level': 'A1', 'skill': 'reading',
                'qtype': 'true_false', 'topic': 'family',
                'title': 'Lisa\'s Family',
                'content': (
                    'My name is Lisa. I have a big family. I have one brother and two sisters. '
                    'My father is a doctor. My mother is a teacher. We have a cat called Mimi.'
                ),
                'question': 'Lisa has two brothers.',
                'explanation': 'Lisa has ONE brother and two sisters.',
                'difficulty': 1, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'A1-READ-FILL-001', 'level': 'A1', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'daily_life',
                'title': 'Complete the Sentence',
                'question': 'My name ___ Sara. I ___ from Thailand.',
                'correct_answer': 'is|am',
                'explanation': '"My name IS Sara" and "I AM from Thailand" use the verb "be".',
                'difficulty': 1, 'time_limit': 30,
            },
            # ── A1 WRITING ──
            {
                'qid': 'A1-WRIT-SHORT-001', 'level': 'A1', 'skill': 'writing',
                'qtype': 'short_answer', 'topic': 'greetings',
                'title': 'About You',
                'question': 'Write 2-3 sentences about yourself. Say your name, age, and where you are from.',
                'sample_answer': 'My name is Anna. I am 18 years old. I am from Germany.',
                'difficulty': 1, 'time_limit': 120, 'points': 2,
            },
            {
                'qid': 'A1-WRIT-FILL-001', 'level': 'A1', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'daily_life',
                'title': 'Daily Routine Gap Fill',
                'question': 'I wake ___ at 7 o\'clock every morning.',
                'correct_answer': 'up',
                'explanation': '"Wake up" is a phrasal verb meaning to stop sleeping.',
                'difficulty': 1, 'time_limit': 30,
            },
            {
                'qid': 'A1-WRIT-DESC-001', 'level': 'A1', 'skill': 'writing',
                'qtype': 'describe_picture', 'topic': 'family',
                'title': 'Describe a Family Photo',
                'instruction': 'Look at the picture and write 3-4 simple sentences about what you see.',
                'content': (
                    '[Image: A family of four sitting at a dinner table. '
                    'Father, mother, a boy, and a girl. They are eating and smiling.]'
                ),
                'question': 'Describe the family in the picture.',
                'sample_answer': (
                    'I see a family. There are four people. They are eating dinner. '
                    'The father and mother are smiling. A boy and a girl are at the table.'
                ),
                'difficulty': 2, 'time_limit': 180, 'points': 3,
            },
            # ── A1 SPEAKING ──
            {
                'qid': 'A1-SPEAK-INTRO-001', 'level': 'A1', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'greetings',
                'title': 'Introduce Yourself',
                'question': (
                    'Say hello and introduce yourself. Tell me your name, '
                    'where you are from, and one thing you like.'
                ),
                'sample_answer': (
                    'Hello! My name is Sara. I am from Thailand. I like cooking.'
                ),
                'difficulty': 1, 'time_limit': 60, 'points': 2,
            },
            {
                'qid': 'A1-SPEAK-DESC-001', 'level': 'A1', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'family',
                'title': 'Describe Your Family',
                'content': '[Imagine a picture of a family at home in the living room.]',
                'question': 'Describe a family at home. Who do you see? What are they doing?',
                'sample_answer': (
                    'I see a mother and a father. The mother is reading a book. '
                    'The father is watching TV. Two children are playing.'
                ),
                'difficulty': 2, 'time_limit': 90, 'points': 2,
            },
            {
                'qid': 'A1-SPEAK-READ-001', 'level': 'A1', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'daily_life',
                'title': 'Read Aloud: My Day',
                'content': (
                    'I wake up at seven. I eat breakfast. I go to school. '
                    'I come home at three. I play with my friends. I go to bed at nine.'
                ),
                'question': 'Read the text above aloud, clearly and slowly.',
                'difficulty': 1, 'time_limit': 60, 'points': 2,
            },
            # ── A1 LISTENING ──
            {
                'qid': 'A1-LIST-MCQ-001', 'level': 'A1', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'greetings',
                'title': 'Meeting Someone New',
                'content': (
                    '[Audio transcript] "Hello, my name is Anna. '
                    'I am from Spain. I am a nurse. I live in Madrid."'
                ),
                'question': 'What does Anna do?',
                'explanation': 'Anna says "I am a nurse."',
                'difficulty': 1, 'time_limit': 45,
                'options': [
                    ('A', 'She is a teacher', False),
                    ('B', 'She is a nurse', True),
                    ('C', 'She is a doctor', False),
                    ('D', 'She is a student', False),
                ],
            },
            {
                'qid': 'A1-LIST-TF-001', 'level': 'A1', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'daily_life',
                'title': 'Sam\'s Pet',
                'content': (
                    '[Audio transcript] "I have a dog. His name is Buddy. '
                    'He is brown and white. He likes to play in the park."'
                ),
                'question': 'Sam has a cat.',
                'explanation': 'Sam says "I have a dog", not a cat.',
                'difficulty': 1, 'time_limit': 30,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'A1-LIST-FILL-001', 'level': 'A1', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'food',
                'title': 'Favorite Food',
                'content': (
                    '[Audio transcript] "My favorite food is pizza. '
                    'I eat pizza every Friday. I like cheese pizza the best."'
                ),
                'question': 'My favorite food is ___.',
                'correct_answer': 'pizza',
                'explanation': 'The speaker says "My favorite food is pizza."',
                'difficulty': 1, 'time_limit': 30,
            },
        ]

    # =================================================================
    # A2 QUESTIONS
    # =================================================================
    def _a2_questions(self):
        return [
            # ── A2 READING ──
            {
                'qid': 'A2-READ-MCQ-001', 'level': 'A2', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'shopping',
                'title': 'A Shopping Trip',
                'content': (
                    'Last Saturday, Maria went to the shopping mall with her friend Kate. '
                    'She bought a blue dress and a pair of shoes. Kate bought a bag. '
                    'They had lunch at a cafe and then went home by bus.'
                ),
                'question': 'How did Maria and Kate go home?',
                'explanation': 'The text says "they went home by bus".',
                'difficulty': 1, 'time_limit': 60,
                'options': [
                    ('A', 'By taxi', False),
                    ('B', 'By train', False),
                    ('C', 'By bus', True),
                    ('D', 'On foot', False),
                ],
            },
            {
                'qid': 'A2-READ-MATCH-001', 'level': 'A2', 'skill': 'reading',
                'qtype': 'matching', 'topic': 'hobbies',
                'title': 'Match Hobbies to Descriptions',
                'question': 'Match each hobby on the left with the correct description on the right.',
                'difficulty': 2, 'time_limit': 90,
                'pairs': [
                    ('Swimming', 'A sport you do in water'),
                    ('Cooking', 'Making food in the kitchen'),
                    ('Reading', 'Looking at books or texts'),
                    ('Photography', 'Taking pictures with a camera'),
                ],
            },
            {
                'qid': 'A2-READ-FILL-001', 'level': 'A2', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'travel',
                'title': 'At the Airport',
                'content': (
                    'When you travel by plane, first you go to the airport. '
                    'You check in at the desk and get your boarding ___.'
                ),
                'question': 'You check in at the desk and get your boarding ___.',
                'correct_answer': 'pass',
                'explanation': 'A "boarding pass" is the document you need to get on a plane.',
                'difficulty': 1, 'time_limit': 45,
            },
            # ── A2 WRITING ──
            {
                'qid': 'A2-WRIT-LETTER-001', 'level': 'A2', 'skill': 'writing',
                'qtype': 'write_letter', 'topic': 'travel',
                'title': 'Postcard from Holiday',
                'question': (
                    'You are on holiday. Write a short postcard (4-5 sentences) '
                    'to your friend. Tell them where you are, what the weather is like, '
                    'and what you have done.'
                ),
                'sample_answer': (
                    'Dear Tom,\n'
                    'I am in Barcelona! The weather is sunny and warm. '
                    'Yesterday I visited a beautiful beach. Today I am going to a museum. '
                    'I am having a great time!\n'
                    'See you soon,\nMaria'
                ),
                'difficulty': 2, 'time_limit': 300, 'points': 3,
            },
            {
                'qid': 'A2-WRIT-SHORT-001', 'level': 'A2', 'skill': 'writing',
                'qtype': 'short_answer', 'topic': 'hobbies',
                'title': 'Your Free Time',
                'question': 'What do you like to do in your free time? Write 3-4 sentences.',
                'sample_answer': (
                    'In my free time, I like to play basketball with my friends. '
                    'I also enjoy watching movies at home. Sometimes I cook Thai food. '
                    'On weekends, I go to the park.'
                ),
                'difficulty': 1, 'time_limit': 180, 'points': 2,
            },
            {
                'qid': 'A2-WRIT-FILL-001', 'level': 'A2', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'daily_life',
                'title': 'Past Tense Gap Fill',
                'question': 'Yesterday, I ___ (go) to the supermarket and ___ (buy) some fruit.',
                'correct_answer': 'went|bought',
                'explanation': 'Go -> went (past), buy -> bought (past).',
                'difficulty': 2, 'time_limit': 45,
            },
            # ── A2 SPEAKING ──
            {
                'qid': 'A2-SPEAK-OPIN-001', 'level': 'A2', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'hobbies',
                'title': 'Your Favorite Hobby',
                'question': (
                    'What is your favorite hobby? Why do you like it? '
                    'How often do you do it? Talk for about 1 minute.'
                ),
                'sample_answer': (
                    'My favorite hobby is playing football. I like it because it is fun '
                    'and I can play with my friends. I play football three times a week. '
                    'I usually play in the park near my house.'
                ),
                'difficulty': 1, 'time_limit': 90, 'points': 2,
            },
            {
                'qid': 'A2-SPEAK-DESC-001', 'level': 'A2', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'shopping',
                'title': 'Busy Market Scene',
                'content': (
                    '[Image: A busy outdoor market with fruit stalls, '
                    'people shopping, a vendor selling vegetables, children eating ice cream.]'
                ),
                'question': 'Describe what you see in this market scene. What are the people doing?',
                'sample_answer': (
                    'I can see a busy market. There are many fruit and vegetable stalls. '
                    'A woman is buying apples. Some children are eating ice cream. '
                    'A man is selling vegetables. It looks like a sunny day.'
                ),
                'difficulty': 2, 'time_limit': 90, 'points': 2,
            },
            {
                'qid': 'A2-SPEAK-READ-001', 'level': 'A2', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'travel',
                'title': 'Read Aloud: A Trip',
                'content': (
                    'Last summer, I went on a trip to the beach with my family. '
                    'We stayed in a small hotel near the sea. Every morning, '
                    'we walked on the beach and collected shells. In the afternoon, '
                    'we swam in the sea. It was a wonderful holiday.'
                ),
                'question': 'Read this passage aloud clearly.',
                'difficulty': 1, 'time_limit': 60, 'points': 2,
            },
            # ── A2 LISTENING ──
            {
                'qid': 'A2-LIST-MCQ-001', 'level': 'A2', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'shopping',
                'title': 'At the Clothes Shop',
                'content': (
                    '[Audio transcript] Customer: "Excuse me, how much is this red T-shirt?" '
                    'Shop assistant: "It\'s 15 dollars. But we have a sale today - it\'s only 10 dollars." '
                    'Customer: "Great, I\'ll take it."'
                ),
                'question': 'How much does the customer pay for the T-shirt?',
                'explanation': 'The sale price is 10 dollars.',
                'difficulty': 1, 'time_limit': 45,
                'options': [
                    ('A', '5 dollars', False),
                    ('B', '10 dollars', True),
                    ('C', '15 dollars', False),
                    ('D', '20 dollars', False),
                ],
            },
            {
                'qid': 'A2-LIST-TF-001', 'level': 'A2', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'health',
                'title': 'Doctor\'s Advice',
                'content': (
                    '[Audio transcript] Doctor: "You need to drink more water. '
                    'Try to drink at least 8 glasses every day. Also, you should '
                    'eat more fruit and vegetables. And try to sleep 8 hours a night."'
                ),
                'question': 'The doctor says you should drink at least 6 glasses of water every day.',
                'explanation': 'The doctor says 8 glasses, not 6.',
                'difficulty': 2, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'A2-LIST-FILL-001', 'level': 'A2', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'travel',
                'title': 'Train Announcement',
                'content': (
                    '[Audio transcript] "Attention please. The train to Manchester '
                    'will depart from platform 3 in 10 minutes."'
                ),
                'question': 'The train to Manchester will depart from platform ___.',
                'correct_answer': '3|three',
                'explanation': 'The announcement says "platform 3".',
                'difficulty': 1, 'time_limit': 30,
            },
        ]

    # =================================================================
    # B1 QUESTIONS
    # =================================================================
    def _b1_questions(self):
        return [
            # ── B1 READING ──
            {
                'qid': 'B1-READ-MCQ-001', 'level': 'B1', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'technology',
                'title': 'Social Media Effects',
                'content': (
                    'Social media has changed the way people communicate. While it helps '
                    'people stay connected with friends and family around the world, some '
                    'researchers are concerned about its effects on mental health. Studies '
                    'show that spending too much time on social media can lead to feelings '
                    'of loneliness and anxiety, especially among teenagers.'
                ),
                'question': 'According to the passage, what is a concern about social media?',
                'explanation': 'The passage mentions effects on mental health including loneliness and anxiety.',
                'difficulty': 1, 'time_limit': 90,
                'options': [
                    ('A', 'It is too expensive to use', False),
                    ('B', 'It can cause loneliness and anxiety', True),
                    ('C', 'It does not work in all countries', False),
                    ('D', 'It is only for young people', False),
                ],
            },
            {
                'qid': 'B1-READ-ORDER-001', 'level': 'B1', 'skill': 'reading',
                'qtype': 'ordering', 'topic': 'education',
                'title': 'Steps to Apply to University',
                'question': 'Put these steps for applying to university in the correct order.',
                'difficulty': 2, 'time_limit': 90,
                'order_items': [
                    'Research universities and courses',
                    'Prepare your application documents',
                    'Submit your application before the deadline',
                    'Attend an interview if required',
                    'Receive your acceptance letter',
                ],
            },
            {
                'qid': 'B1-READ-FILL-001', 'level': 'B1', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'environment',
                'title': 'Climate Change',
                'content': (
                    'Climate change is one of the biggest ___ facing our planet today. '
                    'Scientists say we need to reduce our carbon footprint.'
                ),
                'question': 'Climate change is one of the biggest ___ facing our planet today.',
                'correct_answer': 'challenges|problems|issues',
                'explanation': 'Common collocations: "biggest challenges/problems/issues".',
                'difficulty': 2, 'time_limit': 45,
            },
            # ── B1 WRITING ──
            {
                'qid': 'B1-WRIT-ESSAY-001', 'level': 'B1', 'skill': 'writing',
                'qtype': 'opinion_essay', 'topic': 'education',
                'title': 'Online vs. Classroom Learning',
                'question': (
                    'Some people prefer online learning, while others prefer '
                    'traditional classroom learning. What is your opinion? '
                    'Write 80-100 words giving reasons for your view.'
                ),
                'sample_answer': (
                    'I think both online and classroom learning have advantages. '
                    'Classroom learning is better for social interaction and asking questions. '
                    'However, online learning is more flexible and convenient. Students can '
                    'study at their own pace and review materials anytime. On the other hand, '
                    'online learners may feel isolated. In my opinion, a mix of both methods '
                    'would be the best solution for most students.'
                ),
                'difficulty': 2, 'time_limit': 600, 'points': 5,
            },
            {
                'qid': 'B1-WRIT-LETTER-001', 'level': 'B1', 'skill': 'writing',
                'qtype': 'write_letter', 'topic': 'work',
                'title': 'Email to a Colleague',
                'question': (
                    'Write an email to your colleague asking them to help you '
                    'with a project. Explain what the project is about, why you '
                    'need help, and suggest a time to meet. Write 60-80 words.'
                ),
                'sample_answer': (
                    'Dear Sarah,\n\n'
                    'I hope you are well. I am writing to ask for your help with '
                    'the marketing presentation for next week\'s meeting. I need '
                    'to prepare the slides and collect some data, but I am running '
                    'out of time. Would you be free to meet on Wednesday afternoon '
                    'to discuss this? I would really appreciate your support.\n\n'
                    'Best regards,\nDavid'
                ),
                'difficulty': 2, 'time_limit': 480, 'points': 4,
            },
            {
                'qid': 'B1-WRIT-FILL-001', 'level': 'B1', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'environment',
                'title': 'Conditional Sentences',
                'question': 'If we ___ (not reduce) pollution, the environment will get worse.',
                'correct_answer': 'don\'t reduce|do not reduce',
                'explanation': 'First conditional: If + present simple, will + infinitive.',
                'difficulty': 2, 'time_limit': 45,
            },
            # ── B1 SPEAKING ──
            {
                'qid': 'B1-SPEAK-OPIN-001', 'level': 'B1', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'technology',
                'title': 'Social Media: Good or Bad?',
                'question': (
                    'Do you think social media is mostly good or mostly bad for young people? '
                    'Give your opinion with reasons and examples. Speak for about 2 minutes.'
                ),
                'sample_answer': (
                    'I think social media is both good and bad. On the positive side, it helps '
                    'young people stay in touch with friends and learn about the world. However, '
                    'spending too much time on social media can be harmful. Young people may '
                    'compare themselves to others and feel sad. Also, there is the problem of '
                    'cyberbullying. Overall, I think social media is useful but we need to use it carefully.'
                ),
                'difficulty': 2, 'time_limit': 150, 'points': 3,
            },
            {
                'qid': 'B1-SPEAK-DESC-001', 'level': 'B1', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'work',
                'title': 'Office Scene',
                'content': (
                    '[Image: An open-plan office. Some people are working on computers, '
                    'two colleagues are having a meeting at a whiteboard, '
                    'one person is on a phone call, another is drinking coffee by the window.]'
                ),
                'question': 'Describe what is happening in the office. What are the people doing?',
                'sample_answer': (
                    'This is a modern office. Several people are working at their computers. '
                    'In the back, two colleagues are having a meeting near a whiteboard. '
                    'One person is talking on the phone, and another is taking a break '
                    'drinking coffee by the window. The office looks busy but organized.'
                ),
                'difficulty': 2, 'time_limit': 120, 'points': 3,
            },
            {
                'qid': 'B1-SPEAK-READ-001', 'level': 'B1', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'environment',
                'title': 'Read Aloud: Recycling',
                'content': (
                    'Recycling is one of the easiest ways to help the environment. '
                    'By separating our waste into different bins, we can reduce the amount '
                    'of rubbish that goes to landfill. Paper, glass, and plastic can all be '
                    'recycled and turned into new products. This saves energy and helps '
                    'protect our natural resources for future generations.'
                ),
                'question': 'Read this passage aloud with clear pronunciation and natural intonation.',
                'difficulty': 2, 'time_limit': 90, 'points': 2,
            },
            # ── B1 LISTENING ──
            {
                'qid': 'B1-LIST-MCQ-001', 'level': 'B1', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'work',
                'title': 'Job Interview Advice',
                'content': (
                    '[Audio transcript] "The most important thing in a job interview is '
                    'preparation. Research the company before you go. Think about why you '
                    'want to work there and what skills you can offer. Also, remember to '
                    'dress professionally and arrive 10 minutes early."'
                ),
                'question': 'According to the speaker, what is the most important thing in a job interview?',
                'explanation': 'The speaker says preparation is the most important thing.',
                'difficulty': 1, 'time_limit': 60,
                'options': [
                    ('A', 'Wearing expensive clothes', False),
                    ('B', 'Preparation', True),
                    ('C', 'Arriving one hour early', False),
                    ('D', 'Bringing your certificates', False),
                ],
            },
            {
                'qid': 'B1-LIST-TF-001', 'level': 'B1', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'education',
                'title': 'Study Tips',
                'content': (
                    '[Audio transcript] "Research shows that studying in short sessions '
                    'of 25 minutes with 5-minute breaks is more effective than studying '
                    'for hours without a break. This method is called the Pomodoro Technique. '
                    'It helps your brain process information better."'
                ),
                'question': 'The Pomodoro Technique recommends studying for 45 minutes at a time.',
                'explanation': 'The technique recommends 25-minute sessions, not 45.',
                'difficulty': 2, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'B1-LIST-FILL-001', 'level': 'B1', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'technology',
                'title': 'Smartphone Usage',
                'content': (
                    '[Audio transcript] "A recent survey found that the average person '
                    'spends about four hours a day looking at their smartphone."'
                ),
                'question': 'The average person spends about ___ hours a day on their smartphone.',
                'correct_answer': 'four|4',
                'explanation': 'The audio says "about four hours a day".',
                'difficulty': 1, 'time_limit': 30,
            },
        ]

    # =================================================================
    # B2 QUESTIONS
    # =================================================================
    def _b2_questions(self):
        return [
            # ── B2 READING ──
            {
                'qid': 'B2-READ-MCQ-001', 'level': 'B2', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'science',
                'title': 'Artificial Intelligence in Healthcare',
                'content': (
                    'Artificial intelligence is transforming healthcare in remarkable ways. '
                    'AI algorithms can now analyze medical images with accuracy comparable '
                    'to experienced radiologists. Machine learning models can predict patient '
                    'outcomes and identify potential health risks before symptoms appear. '
                    'However, critics argue that over-reliance on AI could diminish the '
                    'importance of the doctor-patient relationship and human judgment.'
                ),
                'question': 'What concern about AI in healthcare is mentioned in the text?',
                'explanation': 'The text mentions over-reliance on AI diminishing human judgment.',
                'difficulty': 2, 'time_limit': 90,
                'options': [
                    ('A', 'AI is too expensive for hospitals', False),
                    ('B', 'AI might reduce the value of human judgment', True),
                    ('C', 'AI cannot analyze medical images', False),
                    ('D', 'AI will replace all doctors', False),
                ],
            },
            {
                'qid': 'B2-READ-MATCH-001', 'level': 'B2', 'skill': 'reading',
                'qtype': 'matching', 'topic': 'media',
                'title': 'Media Types and Functions',
                'question': 'Match each type of media with its primary function.',
                'difficulty': 2, 'time_limit': 90,
                'pairs': [
                    ('Investigative journalism', 'Uncovering hidden truths and corruption'),
                    ('Editorial', 'Expressing the opinion of the publication'),
                    ('Feature article', 'Providing in-depth coverage of a topic'),
                    ('News report', 'Delivering factual accounts of current events'),
                ],
            },
            {
                'qid': 'B2-READ-FILL-001', 'level': 'B2', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'politics',
                'title': 'Democracy and Participation',
                'content': (
                    'In a healthy democracy, citizen ___ is essential. People need to '
                    'exercise their right to vote and engage in public discourse.'
                ),
                'question': 'In a healthy democracy, citizen ___ is essential.',
                'correct_answer': 'participation|engagement|involvement',
                'explanation': 'Key collocations: citizen participation/engagement/involvement.',
                'difficulty': 2, 'time_limit': 60,
            },
            # ── B2 WRITING ──
            {
                'qid': 'B2-WRIT-ESSAY-001', 'level': 'B2', 'skill': 'writing',
                'qtype': 'opinion_essay', 'topic': 'science',
                'title': 'Should Genetic Engineering Be Allowed?',
                'question': (
                    'Some people believe genetic engineering could solve many of '
                    'humanity\'s problems, while others think it is dangerous. '
                    'Write an essay (120-150 words) discussing both sides and '
                    'give your opinion.'
                ),
                'sample_answer': (
                    'Genetic engineering is one of the most controversial topics in modern science. '
                    'Supporters argue it could eliminate hereditary diseases and increase food production. '
                    'For example, genetically modified crops could help feed growing populations. '
                    'On the other hand, opponents worry about unforeseen consequences and ethical issues. '
                    'If we modify human genes, we risk creating inequality between those who can '
                    'afford treatments and those who cannot. Furthermore, altering natural ecosystems '
                    'could have devastating effects. In my view, genetic engineering should be allowed '
                    'but strictly regulated, with transparent oversight.'
                ),
                'difficulty': 2, 'time_limit': 900, 'points': 5,
            },
            {
                'qid': 'B2-WRIT-LETTER-001', 'level': 'B2', 'skill': 'writing',
                'qtype': 'write_letter', 'topic': 'media',
                'title': 'Formal Complaint Letter',
                'question': (
                    'Write a formal letter (100-120 words) to a newspaper editor '
                    'complaining about inaccurate reporting on a local issue. '
                    'Explain what was wrong and suggest what should be done.'
                ),
                'sample_answer': (
                    'Dear Editor,\n\n'
                    'I am writing to express my concern regarding the article published '
                    'on 15 March about the proposed development in Riverside Park. '
                    'The article stated that the community overwhelmingly supports the project, '
                    'which is inaccurate. Having attended the public consultation myself, I can '
                    'confirm that the majority of residents raised significant objections.\n\n'
                    'I would appreciate it if you could publish a correction and include the '
                    'perspectives of local residents who oppose the development.\n\n'
                    'Yours sincerely,\nJohn Williams'
                ),
                'difficulty': 3, 'time_limit': 720, 'points': 5,
            },
            {
                'qid': 'B2-WRIT-FILL-001', 'level': 'B2', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'politics',
                'title': 'Passive Voice Transformation',
                'question': (
                    'The new law ___ (approve) by the parliament last week.'
                ),
                'correct_answer': 'was approved',
                'explanation': 'Passive voice past simple: was/were + past participle.',
                'difficulty': 2, 'time_limit': 45,
            },
            # ── B2 SPEAKING ──
            {
                'qid': 'B2-SPEAK-OPIN-001', 'level': 'B2', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'media',
                'title': 'Fake News and Media Literacy',
                'question': (
                    'How can we combat the spread of fake news? '
                    'Discuss the role of education, social media platforms, and individuals. '
                    'Speak for 2-3 minutes with structured arguments.'
                ),
                'sample_answer': (
                    'Fake news is a growing problem in our digital age. I believe combating it '
                    'requires a multi-pronged approach. Firstly, education is crucial - schools '
                    'should teach media literacy and critical thinking skills. Secondly, social '
                    'media platforms need to take more responsibility by using fact-checking tools '
                    'and labeling unverified content. Finally, individuals must develop the habit '
                    'of verifying information before sharing it. If we all play our part, we can '
                    'significantly reduce the impact of misinformation.'
                ),
                'difficulty': 2, 'time_limit': 180, 'points': 4,
            },
            {
                'qid': 'B2-SPEAK-DESC-001', 'level': 'B2', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'environment',
                'title': 'Environmental Contrast',
                'content': (
                    '[Image: Split image - left side shows a pristine forest with clean river; '
                    'right side shows the same area with deforestation, pollution, and trash.]'
                ),
                'question': (
                    'Compare and contrast these two images. What has changed? '
                    'What might have caused these changes? Suggest solutions.'
                ),
                'sample_answer': (
                    'These two images show a dramatic contrast. The left shows a beautiful, '
                    'pristine forest with a clean river, while the right shows the devastating '
                    'effects of deforestation and pollution. The causes could include industrial '
                    'development, illegal logging, and inadequate waste management. To address this, '
                    'governments should enforce stricter environmental laws and promote reforestation.'
                ),
                'difficulty': 3, 'time_limit': 150, 'points': 4,
            },
            {
                'qid': 'B2-SPEAK-READ-001', 'level': 'B2', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'science',
                'title': 'Read Aloud: Space Exploration',
                'content': (
                    'Space exploration has always captivated the human imagination. '
                    'From the first moon landing in 1969 to the recent Mars rover missions, '
                    'humanity has continuously pushed the boundaries of what is possible. '
                    'Private companies are now joining the effort, making space travel more '
                    'accessible than ever before. However, the challenges remain enormous, '
                    'including radiation exposure, psychological isolation, and the immense '
                    'distances involved in interplanetary travel.'
                ),
                'question': 'Read this passage with appropriate expression, stress, and intonation.',
                'difficulty': 2, 'time_limit': 90, 'points': 3,
            },
            # ── B2 LISTENING ──
            {
                'qid': 'B2-LIST-MCQ-001', 'level': 'B2', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'science',
                'title': 'Climate Science Lecture',
                'content': (
                    '[Audio transcript] "The Paris Agreement, signed in 2015, aims to limit '
                    'global warming to 1.5 degrees Celsius above pre-industrial levels. '
                    'However, current commitments by nations are insufficient. Scientists '
                    'estimate that without drastic action, temperatures could rise by '
                    '3 degrees by the end of the century, leading to catastrophic consequences '
                    'including rising sea levels and extreme weather events."'
                ),
                'question': 'What temperature increase does the Paris Agreement aim to prevent?',
                'explanation': 'The Paris Agreement aims to limit warming to 1.5 degrees Celsius.',
                'difficulty': 2, 'time_limit': 60,
                'options': [
                    ('A', '0.5 degrees Celsius', False),
                    ('B', '1.5 degrees Celsius', True),
                    ('C', '3 degrees Celsius', False),
                    ('D', '5 degrees Celsius', False),
                ],
            },
            {
                'qid': 'B2-LIST-TF-001', 'level': 'B2', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'politics',
                'title': 'Voter Turnout Discussion',
                'content': (
                    '[Audio transcript] "In many democracies, voter turnout has been '
                    'declining steadily over the past few decades. Some countries have '
                    'introduced compulsory voting to address this, such as Australia, '
                    'where failure to vote can result in a fine. Critics argue that '
                    'forcing people to vote does not guarantee informed participation."'
                ),
                'question': 'In Australia, voting is voluntary.',
                'explanation': 'Australia has compulsory (mandatory) voting.',
                'difficulty': 2, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'B2-LIST-FILL-001', 'level': 'B2', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'media',
                'title': 'Podcast on Digital Media',
                'content': (
                    '[Audio transcript] "The rise of streaming platforms has fundamentally '
                    'altered the entertainment landscape, with traditional television '
                    'networks losing approximately 30 percent of their audience."'
                ),
                'question': 'Traditional TV networks have lost approximately ___ percent of their audience.',
                'correct_answer': '30|thirty',
                'explanation': 'The speaker says "approximately 30 percent".',
                'difficulty': 2, 'time_limit': 30,
            },
        ]

    # =================================================================
    # C1 QUESTIONS
    # =================================================================
    def _c1_questions(self):
        return [
            # ── C1 READING ──
            {
                'qid': 'C1-READ-MCQ-001', 'level': 'C1', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'business',
                'title': 'Corporate Social Responsibility',
                'content': (
                    'The concept of corporate social responsibility (CSR) has evolved '
                    'significantly over the past century. Initially viewed as mere philanthropy, '
                    'CSR now encompasses a company\'s economic, environmental, and social impact. '
                    'Critics of CSR argue that a corporation\'s primary obligation is to its '
                    'shareholders, as articulated by Milton Friedman. However, proponents contend '
                    'that businesses ignoring their broader societal obligations do so at their '
                    'own long-term peril, as consumer awareness and regulatory scrutiny intensify.'
                ),
                'question': 'What is Milton Friedman\'s position on CSR as described in the text?',
                'explanation': 'Friedman argued a corporation\'s primary obligation is to its shareholders.',
                'difficulty': 2, 'time_limit': 120,
                'options': [
                    ('A', 'Companies should donate more to charity', False),
                    ('B', 'A corporation\'s main duty is to its shareholders', True),
                    ('C', 'CSR should be regulated by government', False),
                    ('D', 'Businesses should ignore profit and focus on society', False),
                ],
            },
            {
                'qid': 'C1-READ-MATCH-001', 'level': 'C1', 'skill': 'reading',
                'qtype': 'matching', 'topic': 'academic',
                'title': 'Research Methodologies',
                'question': 'Match each research method with its description.',
                'difficulty': 3, 'time_limit': 120,
                'pairs': [
                    ('Qualitative research', 'Explores perspectives through interviews and observations'),
                    ('Quantitative research', 'Collects numerical data for statistical analysis'),
                    ('Mixed methods', 'Combines both numerical and narrative data collection'),
                    ('Case study', 'In-depth examination of a single instance or event'),
                ],
            },
            {
                'qid': 'C1-READ-FILL-001', 'level': 'C1', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'philosophy',
                'title': 'Ethical Reasoning',
                'content': (
                    'The philosophical concept of the "social ___" suggests that individuals '
                    'consent to surrender certain freedoms to a governing authority in exchange '
                    'for the protection of their remaining rights.'
                ),
                'question': 'The philosophical concept of the "social ___" suggests that...',
                'correct_answer': 'contract',
                'explanation': '"Social contract" is a key concept in political philosophy (Rousseau, Locke).',
                'difficulty': 2, 'time_limit': 60,
            },
            # ── C1 WRITING ──
            {
                'qid': 'C1-WRIT-ESSAY-001', 'level': 'C1', 'skill': 'writing',
                'qtype': 'opinion_essay', 'topic': 'business',
                'title': 'Remote Work: A Permanent Shift?',
                'question': (
                    'Some argue that remote work will permanently replace traditional office work. '
                    'Write a well-structured essay (150-200 words) evaluating this claim. '
                    'Consider economic, social, and psychological factors.'
                ),
                'sample_answer': (
                    'The shift towards remote work, accelerated by the pandemic, has prompted debate '
                    'about whether it represents a permanent transformation. Economically, remote work '
                    'offers significant advantages: companies can reduce overhead costs while employees '
                    'save on commuting. However, the picture is more nuanced than it appears.\n\n'
                    'From a social perspective, prolonged remote work can erode team cohesion and '
                    'spontaneous collaboration. The psychological toll is also notable, with studies '
                    'indicating increased burnout rates among remote workers who struggle to maintain '
                    'work-life boundaries.\n\n'
                    'Rather than a complete replacement, a hybrid model appears most viable, combining '
                    'the flexibility of remote work with the collaborative benefits of physical presence.'
                ),
                'difficulty': 3, 'time_limit': 1200, 'points': 6,
            },
            {
                'qid': 'C1-WRIT-LETTER-001', 'level': 'C1', 'skill': 'writing',
                'qtype': 'write_letter', 'topic': 'academic',
                'title': 'Research Proposal Cover Letter',
                'question': (
                    'Write a formal cover letter (120-150 words) to accompany a research '
                    'grant application. Outline your research topic, its significance, '
                    'and why it deserves funding.'
                ),
                'sample_answer': (
                    'Dear Grant Committee Members,\n\n'
                    'I am writing to submit my application for the 2025 Research Innovation '
                    'Grant in support of my project examining the sociolinguistic factors '
                    'influencing second language acquisition in multilingual communities.\n\n'
                    'This research addresses a critical gap in our understanding of how '
                    'multilingual environments affect language learning outcomes. The findings '
                    'could significantly improve pedagogical approaches in diverse classrooms. '
                    'My methodology combines quantitative analysis of proficiency data with '
                    'qualitative interviews of both learners and educators.\n\n'
                    'I believe this project aligns closely with the fund\'s mission to support '
                    'innovative language education research.\n\n'
                    'Yours faithfully,\nDr. Sarah Chen'
                ),
                'difficulty': 3, 'time_limit': 900, 'points': 6,
            },
            {
                'qid': 'C1-WRIT-FILL-001', 'level': 'C1', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'philosophy',
                'title': 'Advanced Vocabulary',
                'question': (
                    'The government\'s decision to ___ the controversial policy '
                    'was met with widespread criticism from opposition parties.'
                ),
                'correct_answer': 'implement|enforce|enact',
                'explanation': 'Common advanced collocations with "policy".',
                'difficulty': 2, 'time_limit': 45,
            },
            # ── C1 SPEAKING ──
            {
                'qid': 'C1-SPEAK-OPIN-001', 'level': 'C1', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'philosophy',
                'title': 'Ethics of Artificial Intelligence',
                'question': (
                    'Should AI systems be given legal personhood? Discuss the ethical, '
                    'legal, and philosophical implications. Present a well-structured '
                    'argument with counterpoints. Speak for 3-4 minutes.'
                ),
                'sample_answer': (
                    'The question of AI legal personhood raises profound philosophical and legal '
                    'challenges. While granting AI some form of legal status could clarify liability '
                    'when autonomous systems cause harm, it fundamentally challenges our understanding '
                    'of personhood, which has traditionally been linked to consciousness and moral agency. '
                    'The counterargument is compelling: without consciousness, AI cannot truly bear '
                    'responsibility. A more pragmatic approach might involve creating a new legal '
                    'category for AI that addresses accountability without anthropomorphizing machines.'
                ),
                'difficulty': 3, 'time_limit': 240, 'points': 5,
            },
            {
                'qid': 'C1-SPEAK-DESC-001', 'level': 'C1', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'business',
                'title': 'Business Infographic Analysis',
                'content': (
                    '[Image: An infographic showing global trade flows, with arrows between '
                    'continents showing import/export values, bar charts of GDP growth, '
                    'and pie charts of major export categories.]'
                ),
                'question': (
                    'Analyze this infographic about global trade. Describe the key trends, '
                    'identify significant patterns, and discuss their implications.'
                ),
                'sample_answer': (
                    'This infographic presents a comprehensive overview of global trade dynamics. '
                    'The most significant trade flows appear to be between Asia and North America, '
                    'suggesting continued economic interdependence. The GDP growth chart indicates '
                    'emerging economies are outpacing developed nations. The export categories show '
                    'technology dominating, followed by manufactured goods and raw materials.'
                ),
                'difficulty': 3, 'time_limit': 180, 'points': 5,
            },
            {
                'qid': 'C1-SPEAK-READ-001', 'level': 'C1', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'academic',
                'title': 'Read Aloud: Academic Excerpt',
                'content': (
                    'The epistemological foundations of empirical research rest upon the '
                    'assumption that observable phenomena can be measured, quantified, and '
                    'subsequently analyzed to yield generalizable conclusions. This positivist '
                    'paradigm, while enormously productive in the natural sciences, has been '
                    'increasingly challenged by interpretivist scholars who argue that human '
                    'experience cannot be reduced to mere data points.'
                ),
                'question': 'Read this academic passage with appropriate pacing and emphasis.',
                'difficulty': 3, 'time_limit': 90, 'points': 3,
            },
            # ── C1 LISTENING ──
            {
                'qid': 'C1-LIST-MCQ-001', 'level': 'C1', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'business',
                'title': 'Venture Capital Discussion',
                'content': (
                    '[Audio transcript] "What distinguishes successful startups from failures '
                    'is not merely the quality of their product but their ability to identify '
                    'and capture market timing. Research from Harvard Business School suggests '
                    'that timing accounts for approximately 42 percent of a startup\'s success, '
                    'outweighing factors such as team composition, business model, and funding."'
                ),
                'question': 'According to the Harvard study, what is the most important factor for startup success?',
                'explanation': 'The study says timing accounts for 42% - the highest factor.',
                'difficulty': 2, 'time_limit': 60,
                'options': [
                    ('A', 'Product quality', False),
                    ('B', 'Team composition', False),
                    ('C', 'Market timing', True),
                    ('D', 'Amount of funding', False),
                ],
            },
            {
                'qid': 'C1-LIST-TF-001', 'level': 'C1', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'philosophy',
                'title': 'Cognitive Bias Lecture',
                'content': (
                    '[Audio transcript] "Confirmation bias is the tendency to search for '
                    'and interpret information in a way that confirms one\'s pre-existing '
                    'beliefs. This bias is particularly dangerous in scientific research, '
                    'where researchers may unconsciously design studies that confirm their '
                    'hypotheses rather than genuinely testing them."'
                ),
                'question': 'Confirmation bias helps researchers design better experiments.',
                'explanation': 'Confirmation bias is described as "dangerous" and leading to poor study design.',
                'difficulty': 2, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'C1-LIST-FILL-001', 'level': 'C1', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'academic',
                'title': 'Research Methodology',
                'content': (
                    '[Audio transcript] "The researcher employed a longitudinal ___ design, '
                    'collecting data from the same participants over a period of five years."'
                ),
                'question': 'The researcher employed a longitudinal ___ design.',
                'correct_answer': 'study|research',
                'explanation': '"Longitudinal study/research design" is a common academic term.',
                'difficulty': 2, 'time_limit': 30,
            },
        ]

    # =================================================================
    # C2 QUESTIONS
    # =================================================================
    def _c2_questions(self):
        return [
            # ── C2 READING ──
            {
                'qid': 'C2-READ-MCQ-001', 'level': 'C2', 'skill': 'reading',
                'qtype': 'multiple_choice', 'topic': 'literature',
                'title': 'Literary Analysis: Metaphor',
                'content': (
                    'In the opening of Dickens\' "A Tale of Two Cities", the famous paradoxical '
                    'structure - "It was the best of times, it was the worst of times" - serves '
                    'not merely as rhetorical embellishment but as a precise encapsulation of '
                    'the novel\'s central thesis: that revolutionary upheaval simultaneously '
                    'contains the seeds of both liberation and destruction. The antithetical '
                    'construction mirrors the duality inherent in the human condition itself.'
                ),
                'question': 'What literary function does the passage attribute to Dickens\' opening?',
                'explanation': 'It encapsulates the novel\'s thesis about the dual nature of revolution.',
                'difficulty': 3, 'time_limit': 120,
                'options': [
                    ('A', 'Simple decoration to make the text more interesting', False),
                    ('B', 'A precise summary of the novel\'s central thesis on duality', True),
                    ('C', 'A historical record of events in the French Revolution', False),
                    ('D', 'An example of poor writing style', False),
                ],
            },
            {
                'qid': 'C2-READ-ORDER-001', 'level': 'C2', 'skill': 'reading',
                'qtype': 'ordering', 'topic': 'global_issues',
                'title': 'Logical Argument Structure',
                'question': 'Arrange these components of a diplomatic policy brief in the correct order.',
                'difficulty': 3, 'time_limit': 120,
                'order_items': [
                    'Executive summary outlining key findings',
                    'Historical context and background analysis',
                    'Assessment of current situation and stakeholders',
                    'Evaluation of policy options with risk analysis',
                    'Recommendations and implementation timeline',
                ],
            },
            {
                'qid': 'C2-READ-FILL-001', 'level': 'C2', 'skill': 'reading',
                'qtype': 'fill_in_gaps', 'topic': 'literature',
                'title': 'Advanced Academic Vocabulary',
                'content': (
                    'The author\'s use of ___ - saying the opposite of what is meant - '
                    'creates a layer of meaning that rewards careful, attentive reading.'
                ),
                'question': 'The author\'s use of ___ - saying the opposite of what is meant...',
                'correct_answer': 'irony',
                'explanation': 'Irony is the literary device of saying the opposite of what is meant.',
                'difficulty': 2, 'time_limit': 60,
            },
            # ── C2 WRITING ──
            {
                'qid': 'C2-WRIT-ESSAY-001', 'level': 'C2', 'skill': 'writing',
                'qtype': 'opinion_essay', 'topic': 'global_issues',
                'title': 'Sovereignty in a Globalized World',
                'question': (
                    'To what extent is national sovereignty compatible with effective '
                    'global governance? Write a nuanced, well-argued essay (200-250 words) '
                    'drawing on examples from international law, economics, and diplomacy.'
                ),
                'sample_answer': (
                    'The tension between national sovereignty and global governance represents one '
                    'of the defining paradoxes of the modern era. On one hand, the Westphalian '
                    'principle of state sovereignty remains the cornerstone of international relations. '
                    'On the other, transnational challenges such as climate change, pandemic response, '
                    'and financial regulation demand coordinated action that inevitably encroaches '
                    'upon national autonomy.\n\n'
                    'The European Union offers an instructive case study: member states voluntarily '
                    'cede certain sovereign prerogatives in exchange for collective economic and '
                    'political benefits. However, as Brexit demonstrated, this bargain remains '
                    'contested. Similarly, international trade agreements under the WTO framework '
                    'constrain national policy space while facilitating economic growth.\n\n'
                    'A sustainable model likely involves tiered sovereignty, where nations retain '
                    'authority over domestic affairs while delegating specific competencies to '
                    'supranational bodies for issues that transcend borders.'
                ),
                'difficulty': 3, 'time_limit': 1500, 'points': 8,
            },
            {
                'qid': 'C2-WRIT-LETTER-001', 'level': 'C2', 'skill': 'writing',
                'qtype': 'write_letter', 'topic': 'global_issues',
                'title': 'Position Paper for International Conference',
                'question': (
                    'Write a position paper excerpt (150-180 words) for an international '
                    'conference on AI governance, proposing a framework for ethical AI '
                    'development and deployment across nations.'
                ),
                'sample_answer': (
                    'Position Paper: Toward a Multilateral Framework for Ethical AI Governance\n\n'
                    'The proliferation of artificial intelligence systems across borders necessitates '
                    'a coordinated international response that balances innovation with ethical '
                    'safeguards. This paper proposes a three-pillar framework.\n\n'
                    'First, we advocate for the establishment of binding transparency standards '
                    'requiring AI developers to disclose training data sources and algorithmic '
                    'decision-making processes. Second, we propose a tiered regulatory approach '
                    'classifying AI applications by risk level, with correspondingly stringent '
                    'oversight mechanisms. Third, we recommend the creation of an international '
                    'AI Ethics Board with representation from all member states to adjudicate '
                    'cross-border disputes and set evolving standards.\n\n'
                    'Without such a framework, we risk a regulatory race to the bottom that '
                    'could undermine public trust in AI systems worldwide.'
                ),
                'difficulty': 3, 'time_limit': 1200, 'points': 8,
            },
            {
                'qid': 'C2-WRIT-FILL-001', 'level': 'C2', 'skill': 'writing',
                'qtype': 'fill_in_gaps', 'topic': 'literature',
                'title': 'Nuanced Vocabulary',
                'question': (
                    'The diplomat\'s ___ response carefully avoided committing to '
                    'either position while appearing to address both concerns.'
                ),
                'correct_answer': 'equivocal|ambiguous|noncommittal',
                'explanation': 'Equivocal/ambiguous/noncommittal = deliberately vague or unclear.',
                'difficulty': 3, 'time_limit': 45,
            },
            # ── C2 SPEAKING ──
            {
                'qid': 'C2-SPEAK-OPIN-001', 'level': 'C2', 'skill': 'speaking',
                'qtype': 'opinion_essay', 'topic': 'global_issues',
                'title': 'Technology and Human Identity',
                'question': (
                    'As technology increasingly mediates human experience, discuss whether '
                    'our fundamental understanding of human identity and consciousness is '
                    'being fundamentally altered. Provide a sophisticated, structured argument '
                    'with references to philosophical frameworks. Speak for 4-5 minutes.'
                ),
                'sample_answer': (
                    'The relationship between technology and human identity is perhaps the most '
                    'profound philosophical question of our era. Through the lens of phenomenology, '
                    'we can argue that our tools have always shaped our consciousness - from the '
                    'printing press altering how we organize thought to social media restructuring '
                    'our sense of self. What distinguishes the current moment is the unprecedented '
                    'pace and depth of this transformation. Neural interfaces and AI companions '
                    'challenge the very boundary between self and other, raising questions that '
                    'even Descartes could not have anticipated.'
                ),
                'difficulty': 3, 'time_limit': 300, 'points': 6,
            },
            {
                'qid': 'C2-SPEAK-DESC-001', 'level': 'C2', 'skill': 'speaking',
                'qtype': 'describe_picture', 'topic': 'literature',
                'title': 'Analyze an Abstract Artwork',
                'content': (
                    '[Image: An abstract painting with fragmented geometric shapes in muted '
                    'earth tones, suggesting both urban decay and organic growth, with subtle '
                    'text fragments embedded in the composition.]'
                ),
                'question': (
                    'Provide a critical analysis of this artwork. Consider its formal elements, '
                    'possible symbolic meanings, and how it relates to broader cultural themes. '
                    'Demonstrate sophisticated descriptive language.'
                ),
                'sample_answer': (
                    'This piece exemplifies the tension between geometric rigidity and organic '
                    'fluidity that characterizes much contemporary abstract art. The muted earth '
                    'tones suggest a meditation on impermanence - perhaps the interplay between '
                    'human construction and natural dissolution. The embedded text fragments, '
                    'partially obscured, may comment on the fragmentation of meaning in our '
                    'information-saturated age. The composition invites the viewer to construct '
                    'narrative from ambiguity.'
                ),
                'difficulty': 3, 'time_limit': 240, 'points': 6,
            },
            {
                'qid': 'C2-SPEAK-READ-001', 'level': 'C2', 'skill': 'speaking',
                'qtype': 'read_aloud', 'topic': 'literature',
                'title': 'Read Aloud: Philosophical Text',
                'content': (
                    'The paradox of tolerance, as articulated by Karl Popper, posits that '
                    'unlimited tolerance must eventually lead to the disappearance of tolerance '
                    'itself. If we extend unconditional tolerance even to those who are intolerant, '
                    'and if we are not prepared to defend a tolerant society against the onslaught '
                    'of the intolerant, then the tolerant will be destroyed, and tolerance with them. '
                    'This formulation remains as pertinent today as when it was first conceived.'
                ),
                'question': (
                    'Read this philosophical passage with precision, conveying the logical '
                    'structure through your intonation and pacing.'
                ),
                'difficulty': 3, 'time_limit': 90, 'points': 4,
            },
            # ── C2 LISTENING ──
            {
                'qid': 'C2-LIST-MCQ-001', 'level': 'C2', 'skill': 'listening',
                'qtype': 'multiple_choice', 'topic': 'global_issues',
                'title': 'International Relations Lecture',
                'content': (
                    '[Audio transcript] "The concept of \'soft power\', coined by Joseph Nye, '
                    'refers to a country\'s ability to influence others through attraction rather '
                    'than coercion. Unlike military or economic pressure, soft power operates '
                    'through cultural appeal, political values, and foreign policies perceived '
                    'as legitimate. Critics have argued that the dichotomy between soft and hard '
                    'power is overly simplistic, leading Nye to later propose the concept of '
                    '\'smart power\' - the strategic integration of both approaches."'
                ),
                'question': 'Why did Joseph Nye later develop the concept of "smart power"?',
                'explanation': 'Critics argued the soft/hard power dichotomy was too simplistic.',
                'difficulty': 3, 'time_limit': 90,
                'options': [
                    ('A', 'To replace the idea of soft power entirely', False),
                    ('B', 'To address criticism that the dichotomy was oversimplified', True),
                    ('C', 'To promote military intervention', False),
                    ('D', 'To describe economic sanctions', False),
                ],
            },
            {
                'qid': 'C2-LIST-TF-001', 'level': 'C2', 'skill': 'listening',
                'qtype': 'true_false', 'topic': 'literature',
                'title': 'Postmodern Literary Theory',
                'content': (
                    '[Audio transcript] "Derrida\'s concept of deconstruction does not, as '
                    'commonly misunderstood, seek to destroy meaning. Rather, it aims to '
                    'reveal the inherent instabilities and contradictions within texts that '
                    'are typically suppressed by conventional reading practices. Meaning '
                    'is thus not eliminated but shown to be more complex than it appears."'
                ),
                'question': 'According to the speaker, deconstruction aims to destroy meaning in texts.',
                'explanation': 'The speaker explicitly says this is a common misunderstanding.',
                'difficulty': 3, 'time_limit': 45,
                'options': [
                    ('A', 'True', False),
                    ('B', 'False', True),
                ],
            },
            {
                'qid': 'C2-LIST-FILL-001', 'level': 'C2', 'skill': 'listening',
                'qtype': 'fill_in_gaps', 'topic': 'global_issues',
                'title': 'Geopolitical Analysis',
                'content': (
                    '[Audio transcript] "The doctrine of humanitarian ___ holds that '
                    'the international community has a responsibility to protect populations '
                    'from genocide, war crimes, and crimes against humanity, even when this '
                    'requires overriding national sovereignty."'
                ),
                'question': 'The doctrine of humanitarian ___ holds that...',
                'correct_answer': 'intervention',
                'explanation': '"Humanitarian intervention" is the established term for this doctrine.',
                'difficulty': 3, 'time_limit': 45,
            },
        ]

    # =================================================================
    # SUMMARY
    # =================================================================
    def _print_summary(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=== DATABASE SUMMARY ==='))
        self.stdout.write(f'  CEFR Levels    : {CEFRLevel.objects.count()}')
        self.stdout.write(f'  Skills         : {Skill.objects.count()}')
        self.stdout.write(f'  Question Types : {QuestionType.objects.count()}')
        self.stdout.write(f'  Topics         : {Topic.objects.count()}')
        self.stdout.write(f'  Questions      : {Question.objects.count()}')
        self.stdout.write(f'  Options        : {QuestionOption.objects.count()}')
        self.stdout.write(f'  Matching Pairs : {MatchingPair.objects.count()}')
        self.stdout.write(f'  Ordering Items : {OrderingItem.objects.count()}')
        self.stdout.write('')
        self.stdout.write('  Questions by level:')
        for level in CEFRLevel.objects.all():
            count = Question.objects.filter(cefr_level=level).count()
            self.stdout.write(f'    {level.code}: {count} questions')
        self.stdout.write('')
        self.stdout.write('  Questions by skill:')
        for skill in Skill.objects.all():
            count = Question.objects.filter(skill=skill).count()
            self.stdout.write(f'    {skill.name}: {count} questions')
