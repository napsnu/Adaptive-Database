"""
Seed command: seed_cefr_curriculum
====================================
Populates the full hierarchical question bank:

  DifficultyTier x CEFRLevel x CEFRSubLevel x Skill x QuestionType -> Questions

Hierarchy
---------
  3 difficulty tiers  (beginner / intermediate / advanced)
  6 CEFR levels       (A1-C2)
  3 sublevels each    (level.1 / level.2 / level.3)
  4 skills            (reading / writing / listening / speaking)
  10 questions each   => 3 x 6 x 3 x 4 x 10 = 2160 total questions

The file is designed for easy expansion:
  * Add/edit entries inside QUESTION_BANK (keyed by tier/level/sublevel/skill).
  * Each skill section lists exactly 10 question dicts.
  * The ### EXPAND ### markers show where to add more tiers/levels in the same pattern.

Management command
------------------
    python manage.py seed_cefr_curriculum

Idempotent: uses update_or_create on question_id so it is safe to re-run.
"""

import copy

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from assessment.models import (
    DifficultyTier,
    CEFRLevel,
    CEFRSubLevel,
    Skill,
    Topic,
    QuestionType,
    Question,
    QuestionOption,
    AnswerSample,
)

# ---------------------------------------------------------------------------
# STATIC LOOKUP TABLES
# ---------------------------------------------------------------------------

TIERS = [
    {"code": "beginner",     "name": "Beginner",     "order": 1, "grade_band": "4-5",
     "description": "For learners in Grades 4-5 with little or no prior English exposure."},
    {"code": "intermediate", "name": "Intermediate", "order": 2, "grade_band": "6-7",
     "description": "For learners in Grades 6-7 building on foundational English skills."},
    {"code": "advanced",     "name": "Advanced",     "order": 3, "grade_band": "8-9",
     "description": "For learners in Grades 8-9 developing fluency and accuracy."},
]

LEVELS = [
    ("A1", "Breakthrough",                      1, 0.0,  2.0),
    ("A2", "Waystage",                          2, 2.0,  4.0),
    ("B1", "Threshold",                         3, 4.0,  5.5),
    ("B2", "Vantage",                           4, 5.5,  7.0),
    ("C1", "Effective Operational Proficiency", 5, 7.0,  8.5),
    ("C2", "Mastery",                           6, 8.5, 10.0),
]

# 3 sublevels per CEFR level -> topic title per sublevel
SUBLEVEL_TOPICS = {
    "A1": ["Greetings & Introductions", "Daily Life & Family",   "Food & Health"],
    "A2": ["Shopping & Services",       "Travel & Transport",    "Work & Routines"],
    "B1": ["Media & Technology",        "Health & Lifestyle",    "Education & Careers"],
    "B2": ["Society & Culture",         "Science & Environment", "Business & Finance"],
    "C1": ["Ethics & Philosophy",       "Art & Literature",      "Global Issues"],
    "C2": ["Advanced Research",         "Nuance & Rhetoric",     "Expert Discourse"],
}

SKILLS = [
    ("reading",   "Reading",   1),
    ("writing",   "Writing",   2),
    ("listening", "Listening", 3),
    ("speaking",  "Speaking",  4),
]

# ---------------------------------------------------------------------------
# PEDAGOGICAL PROGRESSION BLUEPRINT
# ---------------------------------------------------------------------------
# This metadata is used as authoring guidance and runtime validation anchors.
# It keeps complexity predictable across:
#   tier -> CEFR level -> sublevel -> skill question set

GRADE_BAND_TARGETS = {
    "beginner": {
        "current": "Grade 4-5",
        "future_extension": "Grade 10-12 starter tracks can branch from this baseline",
    },
    "intermediate": {
        "current": "Grade 6-7",
        "future_extension": "Bridges to Grade 10-12 academic English",
    },
    "advanced": {
        "current": "Grade 8-9",
        "future_extension": "Pre-university register and argumentation",
    },
}

# Tier multiplier signals relative lexical/syntactic load.
TIER_COMPLEXITY_ORDER = {
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
}

# CEFR-level language expectations (used as writing guidance for content batches).
CEFR_COMPLEXITY_GUIDE = {
    "A1": "high-frequency vocabulary, simple present, short concrete sentences",
    "A2": "routine contexts, basic connectors (and/but/because), short paragraph control",
    "B1": "multi-sentence reasoning, everyday abstract topics, clearer discourse markers",
    "B2": "topic development with examples, contrast, and cause-effect precision",
    "C1": "nuanced argument, register control, rhetorical organization",
    "C2": "near-native flexibility, subtle stance, synthesis of complex ideas",
}

# Minimum diversity target by skill: unique qtypes per sublevel skill bank.
SKILL_MIN_VARIETY = {
    "reading": 6,
    "writing": 6,
    "listening": 6,
    "speaking": 6,
}

REQUIRED_QUESTION_KEYS = ("qtype", "prompt", "explanation")

# ---------------------------------------------------------------------------
# QUESTION-TYPE TAXONOMY (full list per the UX brief)
# ---------------------------------------------------------------------------

QUESTION_TYPES = [
    # Reading
    ("multiple_choice",      "Multiple Choice",        "single_choice",   True,
     "Choose the best answer from the options below."),
    ("true_false",           "True / False",           "true_false",      True,
     "Decide whether the statement is True or False."),
    ("fill_in_the_blank",    "Fill in the Blank",      "text_input",      True,
     "Complete the sentence with the correct word or phrase."),
    ("match_heading",        "Match Heading",          "matching",        True,
     "Match each paragraph with the correct heading."),
    ("sequence_order",       "Sequence Order",         "ordering",        True,
     "Put the events in the correct order."),
    ("short_answer",         "Short Answer",           "text_input",      True,
     "Write a short answer to the question."),
    ("synonym_match",        "Synonym Match",          "matching",        True,
     "Match each word with its closest synonym."),
    ("reference_question",   "Reference Question",     "text_input",      True,
     "What does the underlined word refer to in the passage?"),
    ("main_idea",            "Main Idea",              "single_choice",   True,
     "Choose the sentence that best states the main idea."),
    ("detail_scan",          "Detail Scan",            "text_input",      True,
     "Scan the passage and answer the specific question."),
    # Writing
    ("sentence_rewrite",     "Sentence Rewrite",       "text_input",      False,
     "Rewrite the sentence as instructed, keeping the same meaning."),
    ("guided_sentence",      "Guided Sentence",        "text_input",      False,
     "Write a complete sentence using the words given."),
    ("error_correction",     "Error Correction",       "text_input",      True,
     "Find and correct the grammar or spelling error in the sentence."),
    ("ordering_words",       "Ordering Words",         "sentence_build",  True,
     "Arrange the words to form a correct sentence."),
    ("transformation",       "Transformation",         "text_input",      False,
     "Transform the sentence as shown in the example."),
    ("completion",           "Completion",             "text_input",      True,
     "Complete the second sentence so it has the same meaning as the first."),
    ("picture_based_prompt", "Picture-Based Prompt",   "picture_prompt",  False,
     "Look at the picture and write your response."),
    ("opinion_short",        "Short Opinion",          "long_text",       False,
     "Write 3-5 sentences expressing your opinion with one reason."),
    ("guided_paragraph",     "Guided Paragraph",       "long_text",       False,
     "Write a short paragraph (5-8 sentences) using the prompts provided."),
    ("write_letter",         "Write a Letter",         "long_text",       False,
     "Write a short letter or email following the instructions."),
    # Listening
    ("dictation_word",       "Dictation - Word",       "text_input",      True,
     "Listen and write the missing word."),
    ("dictation_sentence",   "Dictation - Sentence",   "text_input",      True,
     "Listen and write the complete sentence."),
    ("speaker_intent",       "Speaker Intent",         "single_choice",   True,
     "Why does the speaker say this?"),
    ("detail_identification","Detail Identification",  "single_choice",   True,
     "Choose the correct detail you hear."),
    ("missing_word",         "Missing Word",           "text_input",      True,
     "What word is missing from the sentence you hear?"),
    ("short_response",       "Short Response",         "text_input",      False,
     "Answer the question in one or two sentences based on what you hear."),
    # Speaking
    ("read_aloud",           "Read Aloud",             "audio",           False,
     "Read the text aloud as clearly and naturally as possible."),
    ("repeat_sentence",      "Repeat Sentence",        "audio",           False,
     "Listen to the sentence and repeat it exactly."),
    ("short_opinion",        "Short Opinion (Spoken)", "audio",           False,
     "Speak for 20-30 seconds to share your opinion."),
    ("describe_picture",     "Describe a Picture",     "audio",           False,
     "Describe what you see in the picture in 30-45 seconds."),
    ("personal_response",    "Personal Response",      "audio",           False,
     "Answer the personal question in 20-30 seconds."),
    ("role_play_response",   "Role-Play Response",     "audio",           False,
     "Respond to the situation as if you are taking part in a conversation."),
    ("guided_speaking",      "Guided Speaking",        "audio",           False,
     "Use the prompts to structure your spoken response."),
    ("compare_two_items",    "Compare Two Items",      "audio",           False,
     "Compare and contrast the two items for 30-45 seconds."),
    ("topic_prompt",         "Topic Prompt",           "audio",           False,
     "Talk about the given topic for 30-60 seconds with reasons."),
    ("sentence_building_oral","Sentence Building (Oral)","audio",         False,
     "Say a complete sentence using the words on screen."),
]

# ---------------------------------------------------------------------------
# QUESTION BANK
# ---------------------------------------------------------------------------
# Structure:
#   QUESTION_BANK[tier_code][level_code][unit_order: 1|2|3][skill_code] = [10 dicts]
#
# Each question dict keys:
#   qtype         : str  - question type code
#   prompt        : str  - the question text shown to the learner
#   content       : str  - passage / transcript / image desc (optional)
#   instruction   : str  - overrides the qtype template (optional)
#   options       : list - [(label, text, is_correct), ...]  for choice types
#   correct       : str  - single correct answer string (objective) or pipe-separated
#   accepted      : list - ["ans1", "ans2", ...] (subjective / multi-accepted)
#   explanation   : str  - shown after attempt
#   speaking_topic: str  - explicit topic for speaking questions
#   match_mode    : str  - override answer_matching_mode (default 'normalized')
#
# ### EXPAND ### - add intermediate/advanced tiers below beginner in the same shape.
# ### EXPAND ### - add A2-C2 levels below A1 in each tier.
# ---------------------------------------------------------------------------

QUESTION_BANK = {

    # =========================================================================
    # TIER: BEGINNER  (Grade 4-5)
    # =========================================================================
    "beginner": {

        # ---- CEFR A1 --------------------------------------------------------
        "A1": {

            # -- Unit 1: Greetings & Introductions ----------------------------
            1: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "Hello! My name is Sam. I am eight years old. I live in London. I like cats and football.",
                        "prompt": "How old is Sam?",
                        "options": [("A","Six",False),("B","Eight",True),("C","Ten",False),("D","Twelve",False)],
                        "correct": "B",
                        "explanation": "The passage says 'I am eight years old.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "My name is Lily. I have one brother. His name is Jack. We live in Paris.",
                        "prompt": "Lily has two brothers.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "Lily has ONE brother, not two.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete the sentence: My name ___ Anna. (use the correct form of 'to be')",
                        "correct": "is",
                        "accepted": ["is"],
                        "explanation": "We say 'My name IS Anna' - third person singular of 'to be'.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "Hi! I am Carlos. I am from Spain. I am a student. I speak Spanish and a little English.",
                        "prompt": "Where is Carlos from?",
                        "options": [("A","France",False),("B","Italy",False),("C","Spain",True),("D","Mexico",False)],
                        "correct": "C",
                        "explanation": "The passage states 'I am from Spain.'",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Hello! My name is Tom. I am from England. I like music and reading books.",
                        "prompt": "What two things does Tom like?",
                        "correct": "music and reading|music and books|reading books and music",
                        "accepted": ["music and reading","music and books","reading books and music","music, reading"],
                        "explanation": "Tom likes music and reading books.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "I am Maya. I am nine years old. I have a dog. I live in a small house near the park.",
                        "prompt": "Maya lives near a park.",
                        "options": [("A","True",True),("B","False",False)],
                        "correct": "A",
                        "explanation": "'I live in a small house near the park.'",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: ___ are you? I am fine, thank you.",
                        "correct": "how",
                        "accepted": ["how","How"],
                        "explanation": "'How are you?' is the standard greeting question.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "This is a card from Peter. He says hello to his new classmates. He tells them his name, his age, and where he lives.",
                        "prompt": "What is the main purpose of Peter's card?",
                        "options": [("A","To ask for help",False),("B","To introduce himself",True),("C","To describe his house",False),("D","To talk about school",False)],
                        "correct": "B",
                        "explanation": "Peter introduces himself by sharing his name, age and location.",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "Hi! My name is Nadia. I am ten years old. I have a sister called Leila. She is seven. We both like painting.",
                        "prompt": "How old is Nadia's sister?",
                        "correct": "seven|7|seven years old|7 years old",
                        "accepted": ["seven","7","seven years old","7 years old"],
                        "explanation": "'She is seven.'",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "This is Ali. He is new at school. His teacher says he is very polite.",
                        "prompt": "What does the word 'he' refer to in 'His teacher says he is very polite'?",
                        "correct": "ali|Ali",
                        "accepted": ["Ali","ali","the student","the new student"],
                        "explanation": "'He' refers to Ali, the new student.",
                        "match_mode": "multi_accepted",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write a sentence using: name / Ben / is / My",
                        "correct": "My name is Ben.",
                        "accepted": ["My name is Ben.", "My name is Ben"],
                        "explanation": "The correct word order is: My name is Ben.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: Nice to ___ you. (meet / meets / meeting)",
                        "correct": "meet",
                        "accepted": ["meet"],
                        "explanation": "'Nice to MEET you' is a fixed greeting expression.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Find and correct the error: 'I are from Thailand.'",
                        "correct": "I am from Thailand.",
                        "accepted": ["I am from Thailand.", "I am from Thailand"],
                        "explanation": "With 'I', we use 'am', not 'are'.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Order the words to make a sentence: years / I / am / ten / old",
                        "correct": "I am ten years old.",
                        "accepted": ["I am ten years old.", "I am ten years old"],
                        "explanation": "Subject + am + age + years + old.",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'My name is Zara. I ___ from Japan.'",
                        "correct": "am",
                        "accepted": ["am"],
                        "explanation": "'I AM from Japan.' - first-person singular of 'to be'.",
                    },
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write a sentence using: school / new / I / am / at",
                        "correct": "I am new at school.",
                        "accepted": ["I am new at school.", "I am new at school"],
                        "explanation": "I am new at school.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite as a question: 'Your name is Amir.' (use 'Is')",
                        "correct": "Is your name Amir?",
                        "accepted": ["Is your name Amir?", "Is your name Amir"],
                        "explanation": "Yes/No question: move 'is' before the subject.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct the sentence: 'She am eight years old.'",
                        "correct": "She is eight years old.",
                        "accepted": ["She is eight years old.", "She is eight years old"],
                        "explanation": "With 'she', we use 'is', not 'am'.",
                    },
                    {
                        "qtype": "short_answer",
                        "prompt": "Write ONE sentence to introduce yourself. Include your name and age.",
                        "accepted": [],
                        "explanation": "A correct response names the learner and states an age.",
                        "match_mode": "ai_graded",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Do you like meeting new people? Write 2-3 sentences with a reason.",
                        "accepted": [],
                        "explanation": "Should include a clear yes/no stance and at least one reason.",
                        "match_mode": "ai_graded",
                    },
                ],

                "listening": [
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] Teacher: Good morning, class! My name is Mrs Brown. I am your new English teacher. I am from Australia.",
                        "prompt": "Where is Mrs Brown from?",
                        "options": [("A","England",False),("B","Australia",True),("C","America",False),("D","Canada",False)],
                        "correct": "B",
                        "explanation": "Mrs Brown says 'I am from Australia.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Boy: Hi, I am Leo. Girl: Nice to meet you, Leo! I am Sara.",
                        "prompt": "The girl's name is Sara.",
                        "options": [("A","True",True),("B","False",False)],
                        "correct": "A",
                        "explanation": "The girl says 'I am Sara.'",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] My ___ is David. I am from New Zealand.",
                        "prompt": "Listen and write the missing word.",
                        "correct": "name",
                        "accepted": ["name"],
                        "explanation": "'My NAME is David' - standard self-introduction.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Hello! I am Kim. I am twelve years old. I have two sisters.",
                        "prompt": "How many sisters does Kim have?",
                        "options": [("A","One",False),("B","Two",True),("C","Three",False),("D","None",False)],
                        "correct": "B",
                        "explanation": "Kim says 'I have two sisters.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Man: Good afternoon. My name is Mr Park. It is nice to meet all of you.",
                        "prompt": "Mr Park says 'Good morning'.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "He says 'Good afternoon', not 'Good morning'.",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] - What is your ___? - My name is Fatima.",
                        "prompt": "What word is missing?",
                        "correct": "name",
                        "accepted": ["name"],
                        "explanation": "'What is your NAME?' is the standard question.",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] I ___ from Korea. I love learning English.",
                        "prompt": "Write the missing word.",
                        "correct": "am",
                        "accepted": ["am"],
                        "explanation": "First person singular of 'to be' is 'am'.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Student: Excuse me. Is this seat free? Teacher: Yes, please sit down.",
                        "prompt": "Why does the student say 'Excuse me'?",
                        "options": [("A","To apologise for a mistake",False),("B","To get attention politely before asking",True),("C","To leave the room",False),("D","To greet the teacher",False)],
                        "correct": "B",
                        "explanation": "'Excuse me' is used to politely attract someone's attention.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] Girl: Hi! My name is Priya. I am nine years old. I am in Grade 4.",
                        "prompt": "What grade is Priya in?",
                        "options": [("A","Grade 3",False),("B","Grade 4",True),("C","Grade 5",False),("D","Grade 6",False)],
                        "correct": "B",
                        "explanation": "Priya says 'I am in Grade 4.'",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] - What is your favourite subject? - I love Maths!",
                        "prompt": "What subject does this person love?",
                        "correct": "maths|math|mathematics",
                        "accepted": ["maths","math","mathematics","Maths","Math","Mathematics"],
                        "explanation": "The person says 'I love Maths!'",
                        "match_mode": "multi_accepted",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Talk about yourself for 30 seconds. Say your name, your age, and where you live.",
                        "speaking_topic": "Introduce yourself: name, age, and where you live.",
                        "instruction": "Speak for 20-30 seconds. You can use simple sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete response includes name, age, and location.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What is your favourite colour? Say one sentence.",
                        "speaking_topic": "My favourite colour is ...",
                        "instruction": "Give a short spoken answer - one sentence is enough.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should name a colour and use 'My favourite colour is ...'",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Hello! My name is Sam. I am ten years old. I live in Bangkok.",
                        "prompt": "Read the passage aloud clearly.",
                        "speaking_topic": "Read-aloud passage: personal introduction.",
                        "instruction": "Read each word clearly. Do not rush.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Learner should read with correct pronunciation and fluency.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "Nice to meet you.",
                        "prompt": "Listen and repeat the sentence.",
                        "speaking_topic": "Repeat: Nice to meet you.",
                        "instruction": "Say the sentence exactly as you hear it.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should closely reproduce the spoken sentence.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "Do you like school? Say YES or NO and give one reason.",
                        "speaking_topic": "Do you like school? Give one reason.",
                        "instruction": "Answer in 2-3 short sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Response should include a clear yes/no and a reason.",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Make a sentence using these words: name / is / My / Clara",
                        "speaking_topic": "Build a sentence with: name, is, My, Clara.",
                        "instruction": "Say the complete sentence aloud.",
                        "correct": "My name is Clara.",
                        "accepted": ["My name is Clara.", "My name is Clara"],
                        "match_mode": "normalized",
                        "explanation": "The correct sentence is: My name is Clara.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Use these prompts and speak for 20-30 seconds: 1) My name is... 2) I am ... years old. 3) I like...",
                        "speaking_topic": "Three-part self-introduction using given prompts.",
                        "instruction": "Use each prompt to make a complete sentence.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should cover all three prompts in natural spoken English.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What is your favourite animal? Why?",
                        "speaking_topic": "My favourite animal is ... because ...",
                        "instruction": "Answer in one or two sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names an animal and gives at least one reason.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Good morning! How are you? I am fine, thank you.",
                        "prompt": "Read this greeting aloud.",
                        "speaking_topic": "Read-aloud: common greeting.",
                        "instruction": "Read naturally, as if talking to a friend.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate, natural reading of a simple greeting.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "A cat and a dog - say one way they are the same and one way they are different.",
                        "speaking_topic": "Compare: cat vs dog (one similarity and one difference).",
                        "instruction": "Use the words 'both', 'but', or 'however'.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should name one similarity and one difference.",
                    },
                ],
            },

            # -- Unit 2: Daily Life & Family ----------------------------------
            2: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "Ana's family is big. She has a mother, a father, two brothers, and a grandmother. They live in a house near the sea.",
                        "prompt": "How many brothers does Ana have?",
                        "options": [("A","One",False),("B","Two",True),("C","Three",False),("D","Four",False)],
                        "correct": "B",
                        "explanation": "'She has ... two brothers.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Tom wakes up at seven o'clock every morning. He brushes his teeth, has breakfast, and walks to school.",
                        "prompt": "Tom drives to school.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "The passage says he 'walks to school', not drives.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: I ___ breakfast at seven o'clock every morning. (have / has / having)",
                        "correct": "have",
                        "accepted": ["have"],
                        "explanation": "First person singular simple present of 'have' is 'have'.",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "Mia helps her mother cook dinner on Fridays. Her brother washes the dishes and her father sweeps the floor.",
                        "prompt": "Who washes the dishes?",
                        "correct": "mia's brother|her brother|the brother|brother",
                        "accepted": ["Mia's brother","her brother","the brother","brother"],
                        "explanation": "'Her brother washes the dishes.'",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "The Chang family has dinner together every evening. They talk about their day, share stories, and laugh together. Family time is important to them.",
                        "prompt": "What is the main idea of this passage?",
                        "options": [("A","The Chang family likes cooking",False),("B","The Chang family values spending time together",True),("C","The Chang family lives in a big house",False),("D","The Chang family talks about school",False)],
                        "correct": "B",
                        "explanation": "The passage focuses on the family's habit of having dinner together.",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Every Saturday, Jack cleans his bedroom. He makes his bed and puts his toys away neatly.",
                        "prompt": "Jack cleans his bedroom on Sundays.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "It is every Saturday, not Sunday.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "Maria's mother is a nurse. She works at a hospital from Monday to Friday. On weekends she rests and spends time with her family.",
                        "prompt": "What does Maria's mother do on weekends?",
                        "options": [("A","She works at the hospital",False),("B","She teaches at school",False),("C","She rests and is with her family",True),("D","She travels abroad",False)],
                        "correct": "C",
                        "explanation": "'On weekends she rests and spends time with her family.'",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Luis has dinner at six o'clock. Then he does his homework for one hour. After that he watches TV for thirty minutes.",
                        "prompt": "What does Luis do after dinner?",
                        "correct": "homework|does his homework|he does his homework",
                        "accepted": ["homework","does his homework","he does his homework"],
                        "explanation": "After dinner Luis does his homework.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "Sam has a little sister. She is only four years old. She likes playing with dolls.",
                        "prompt": "What does 'She' refer to in 'She likes playing with dolls'?",
                        "correct": "sam's sister|the little sister|his sister|the sister",
                        "accepted": ["Sam's sister","the little sister","his sister","the sister"],
                        "explanation": "'She' refers to Sam's little sister.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "sequence_order",
                        "prompt": "Put these morning activities in the correct order: A) Go to school  B) Have breakfast  C) Wake up  D) Brush teeth",
                        "correct": "C, D, B, A",
                        "accepted": ["C D B A","C, D, B, A","CDBA","c d b a"],
                        "explanation": "A typical morning: wake up, brush teeth, have breakfast, go to school.",
                        "match_mode": "multi_accepted",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write a sentence: say what your mother or father does for work.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should include a family member and an occupation.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct this sentence: 'My sister have long hair.'",
                        "correct": "My sister has long hair.",
                        "accepted": ["My sister has long hair.", "My sister has long hair"],
                        "explanation": "Third person singular uses 'has', not 'have'.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: I ___ up at six o'clock every day. (wake / wakes / woke)",
                        "correct": "wake",
                        "accepted": ["wake"],
                        "explanation": "First person singular simple present: 'wake'.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Order: dinner / my / cooks / mother / every / evening",
                        "correct": "My mother cooks dinner every evening.",
                        "accepted": ["My mother cooks dinner every evening.", "My mother cooks dinner every evening"],
                        "explanation": "Subject + verb + object + time expression.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite as a question: 'You have a sister.' (use 'Do')",
                        "correct": "Do you have a sister?",
                        "accepted": ["Do you have a sister?","Do you have a sister"],
                        "explanation": "Do + subject + base verb.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'My brother is ten years old. ___ plays football after school.'",
                        "correct": "He",
                        "accepted": ["He","he"],
                        "explanation": "We use 'He' to avoid repeating 'My brother'.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct: 'We eats breakfast at seven.'",
                        "correct": "We eat breakfast at seven.",
                        "accepted": ["We eat breakfast at seven.", "We eat breakfast at seven"],
                        "explanation": "With 'we', use the base form 'eat', not 'eats'.",
                    },
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write a sentence about what you do after school every day.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should mention an activity with 'after school' in simple present tense.",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Do you like helping at home? Write 2 sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should express an opinion about household chores with a reason.",
                    },
                    {
                        "qtype": "guided_paragraph",
                        "prompt": "Write 4-5 sentences about your daily routine. Use: wake up / go to school / have lunch / go home / sleep.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should cover all five prompts in simple present tense.",
                    },
                ],

                "listening": [
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] Mum: What do you want for breakfast, Jake? Jake: I want toast and orange juice, please.",
                        "prompt": "What does Jake want for breakfast?",
                        "options": [("A","Cereal and milk",False),("B","Eggs and coffee",False),("C","Toast and orange juice",True),("D","Bread and tea",False)],
                        "correct": "C",
                        "explanation": "Jake says 'I want toast and orange juice.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] My name is Sophie. I wake up at half past six. Then I have a shower and get dressed.",
                        "prompt": "Sophie wakes up at seven o'clock.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "Sophie wakes up at half past six (6:30), not seven.",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] I live with my ___, my mother, and my two sisters.",
                        "prompt": "Write the missing word.",
                        "correct": "father|dad",
                        "accepted": ["father","dad"],
                        "explanation": "A typical family sentence: I live with my FATHER ...",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Alice: I go to bed at nine o'clock on school nights. On weekends I stay up until ten.",
                        "prompt": "What time does Alice go to bed on school nights?",
                        "options": [("A","Eight o'clock",False),("B","Nine o'clock",True),("C","Ten o'clock",False),("D","Eleven o'clock",False)],
                        "correct": "B",
                        "explanation": "Alice says 'I go to bed at nine o'clock on school nights.'",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Child: Can I help you wash the dishes, Grandma? Grandma: Of course, dear!",
                        "prompt": "Why does the child speak to Grandma?",
                        "options": [("A","To ask for food",False),("B","To offer to help",True),("C","To ask for permission to go out",False),("D","To say goodnight",False)],
                        "correct": "B",
                        "explanation": "The child offers help by asking 'Can I help you wash the dishes?'",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] My dad ___ for work at eight o'clock every morning.",
                        "prompt": "What word is missing?",
                        "correct": "leaves|goes",
                        "accepted": ["leaves","goes"],
                        "explanation": "Third person singular simple present: 'leaves for work'.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Ben has three pets: a cat, a dog, and a fish. He feeds them every day.",
                        "prompt": "Ben has two pets.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "Ben has THREE pets.",
                    },
                    {
                        "qtype": "dictation_sentence",
                        "content": "[Transcript] She cleans her room every Saturday.",
                        "prompt": "Listen and write the sentence.",
                        "correct": "She cleans her room every Saturday.",
                        "accepted": ["She cleans her room every Saturday.", "She cleans her room every Saturday"],
                        "explanation": "Third person singular simple present with time expression.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Mia: My family has dinner at six-thirty. My brother sets the table and I pour the drinks.",
                        "prompt": "What does Mia do at dinner time?",
                        "options": [("A","She cooks the dinner",False),("B","She sets the table",False),("C","She pours the drinks",True),("D","She washes the dishes",False)],
                        "correct": "C",
                        "explanation": "Mia says 'I pour the drinks.'",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] - Do you help your parents at home? - Yes, I help my mother wash the dishes every day.",
                        "prompt": "What does this person do to help at home?",
                        "correct": "wash the dishes|washes the dishes|help wash dishes",
                        "accepted": ["wash the dishes","washes the dishes","help wash dishes"],
                        "explanation": "The person helps wash the dishes every day.",
                        "match_mode": "multi_accepted",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Talk about your family. Say who is in your family and what one person does.",
                        "speaking_topic": "My family: members and one person's role.",
                        "instruction": "Speak for 20-30 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should name family members and describe one person.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What do you do after school every day? Give one example.",
                        "speaking_topic": "My after-school routine - one activity.",
                        "instruction": "One or two sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names one after-school activity in simple present tense.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Every morning, I wake up at seven. I brush my teeth and have breakfast. Then I go to school.",
                        "prompt": "Read the passage aloud.",
                        "speaking_topic": "Read-aloud: daily morning routine.",
                        "instruction": "Read clearly and at a natural pace.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate reading with clear pronunciation.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Use these prompts: 1) I wake up at... 2) Then I... 3) After school I...",
                        "speaking_topic": "Daily routine using three given prompts.",
                        "instruction": "Make a complete sentence for each prompt.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should cover all three prompts in a natural spoken sequence.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "What is your favourite time of day - morning or evening? Give one reason.",
                        "speaking_topic": "Favourite time of day with a reason.",
                        "instruction": "Speak for about 20 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "States a preference and provides at least one reason.",
                    },
                    {
                        "qtype": "describe_picture",
                        "prompt": "Imagine a picture of a family having dinner together. Describe who you see and what they are doing.",
                        "speaking_topic": "Describe a family dinner scene.",
                        "instruction": "Speak for 30 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should mention people and the activity of eating/talking.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "My mother cooks dinner every evening.",
                        "prompt": "Listen and repeat.",
                        "speaking_topic": "Repeat: My mother cooks dinner every evening.",
                        "instruction": "Say the sentence exactly.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate repetition of a simple sentence.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What does your family do on weekends?",
                        "speaking_topic": "Weekend family activities.",
                        "instruction": "One or two sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names one or two weekend activities.",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Say a sentence using: school / walk / I / to / every / day",
                        "speaking_topic": "Sentence: I walk to school every day.",
                        "correct": "I walk to school every day.",
                        "accepted": ["I walk to school every day.", "I walk to school every day"],
                        "match_mode": "normalized",
                        "explanation": "Correct word order: Subject + verb + place + time.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "Morning and evening - which do you prefer for studying? Say one similarity and one difference.",
                        "speaking_topic": "Compare morning vs evening for studying.",
                        "instruction": "Use 'both' for the similarity and 'but' for the difference.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should use comparative language and mention one similarity and one difference.",
                    },
                ],
            },

            # -- Unit 3: Food & Health ----------------------------------------
            3: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "A healthy breakfast gives you energy for the morning. Good breakfast foods include eggs, fruit, yoghurt, and wholegrain bread. Try to avoid sugary cereals.",
                        "prompt": "Which food does the text say to avoid?",
                        "options": [("A","Eggs",False),("B","Yoghurt",False),("C","Sugary cereals",True),("D","Wholegrain bread",False)],
                        "correct": "C",
                        "explanation": "'Try to avoid sugary cereals.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Drinking eight glasses of water every day is good for your health. Water helps your body stay clean and your skin stay clear.",
                        "prompt": "The text says you should drink eight glasses of water a day.",
                        "options": [("A","True",True),("B","False",False)],
                        "correct": "A",
                        "explanation": "'Drinking eight glasses of water every day is good for your health.'",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: Apples and oranges are types of ___.",
                        "correct": "fruit|fruits",
                        "accepted": ["fruit","fruits"],
                        "explanation": "Apples and oranges are both fruit.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "Vegetables are very good for our bodies. They contain vitamins and minerals that keep us healthy. Doctors say we should eat five portions of fruit and vegetables every day.",
                        "prompt": "What is the main idea?",
                        "options": [("A","Doctors like to eat vegetables",False),("B","Vegetables and fruit are important for good health",True),("C","Vitamins can be bought in a shop",False),("D","We should eat five meals a day",False)],
                        "correct": "B",
                        "explanation": "The passage focuses on why vegetables are good for health.",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "Tim eats a banana at break time. He says it gives him energy. His favourite fruit is mango, but bananas are cheaper.",
                        "prompt": "What is Tim's favourite fruit?",
                        "correct": "mango",
                        "accepted": ["mango"],
                        "explanation": "'His favourite fruit is mango.'",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Fast food like burgers and chips is easy to buy and quick to eat, but eating too much of it can cause health problems over time.",
                        "prompt": "Fast food is good for your health if eaten every day.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "'Eating too much of it can cause health problems.'",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Maria drinks a glass of milk every morning. She says it helps her bones grow strong. She also eats cheese and yoghurt.",
                        "prompt": "What does Maria say milk does for her?",
                        "correct": "helps her bones grow strong|makes bones strong|good for bones|strengthens bones",
                        "accepted": ["helps her bones grow strong","makes bones strong","good for bones","strengthens bones"],
                        "explanation": "'She says it helps her bones grow strong.'",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "You should wash your hands before eating and after using the toilet. This stops germs from spreading and keeps you healthy.",
                        "prompt": "When should you wash your hands?",
                        "options": [("A","Only in the morning",False),("B","Before and after every meal",False),("C","Before eating and after using the toilet",True),("D","Only when hands are dirty",False)],
                        "correct": "C",
                        "explanation": "'Wash your hands before eating and after using the toilet.'",
                    },
                    {
                        "qtype": "sequence_order",
                        "prompt": "Order the steps to make a fruit salad: A) Eat and enjoy  B) Wash the fruit  C) Choose the fruit  D) Cut the fruit  E) Mix in a bowl",
                        "correct": "C, B, D, E, A",
                        "accepted": ["C B D E A","C, B, D, E, A","CBDEA"],
                        "explanation": "Logical steps: choose, wash, cut, mix, eat.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "Rice is a staple food in many countries. It is cheap, filling, and easy to cook.",
                        "prompt": "What does 'It' refer to in 'It is cheap, filling, and easy to cook'?",
                        "correct": "rice|Rice",
                        "accepted": ["rice","Rice"],
                        "explanation": "'It' refers to rice.",
                        "match_mode": "multi_accepted",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write a sentence: name one healthy food and say why you like it.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names a healthy food and gives a simple reason.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct: 'I eats an apple every day.'",
                        "correct": "I eat an apple every day.",
                        "accepted": ["I eat an apple every day.", "I eat an apple every day"],
                        "explanation": "First person singular: 'eat', not 'eats'.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: Carrots and peas are ___. (vegetables / fruits / meats)",
                        "correct": "vegetables",
                        "accepted": ["vegetables"],
                        "explanation": "Carrots and peas are vegetables.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Order: drink / I / water / every / glasses / two / day",
                        "correct": "I drink two glasses of water every day.",
                        "accepted": ["I drink two glasses of water every day.", "I drink two glasses of water every day"],
                        "explanation": "Subject + verb + quantity + noun + time expression.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite as a negative: 'She eats junk food every day.'",
                        "correct": "She does not eat junk food every day.",
                        "accepted": ["She does not eat junk food every day.","She doesn't eat junk food every day.","She does not eat junk food every day","She doesn't eat junk food every day"],
                        "explanation": "Third person singular negative: does not / doesn't + base verb.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'An apple a day keeps ___ away.'",
                        "correct": "the doctor|the doctors",
                        "accepted": ["the doctor","the doctors"],
                        "explanation": "The proverb is: 'An apple a day keeps the doctor away.'",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct: 'Milk are good for you.'",
                        "correct": "Milk is good for you.",
                        "accepted": ["Milk is good for you.", "Milk is good for you"],
                        "explanation": "'Milk' is uncountable - use 'is', not 'are'.",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Is fast food bad for you? Write 2-3 sentences with a reason.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Should take a clear position and give at least one reason.",
                    },
                    {
                        "qtype": "guided_paragraph",
                        "prompt": "Write 4-5 sentences about what you eat for breakfast. Use: I eat / I drink / I do not like / because / every morning.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Covers typical breakfast items and uses target vocabulary.",
                    },
                    {
                        "qtype": "picture_based_prompt",
                        "prompt": "Imagine a picture of a bowl of salad. Write 2 sentences: what it contains and why it is healthy.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names at least one ingredient and gives a health reason.",
                    },
                ],

                "listening": [
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] Nurse: You should drink more water and eat less sugar. These are the most important changes for good health.",
                        "prompt": "What change does the nurse say is most important?",
                        "options": [("A","Exercise more and sleep more",False),("B","Drink more water and eat less sugar",True),("C","Eat more fruit and fewer vegetables",False),("D","Take vitamins every night",False)],
                        "correct": "B",
                        "explanation": "The nurse says 'drink more water and eat less sugar'.",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Today's lunch is rice with chicken and salad. There is also fruit for dessert. No sweets today!",
                        "prompt": "Today's lunch includes sweets.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "'No sweets today!'",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] You should eat at least five ___ of fruit and vegetables every day.",
                        "prompt": "Write the missing word.",
                        "correct": "portions|servings|pieces",
                        "accepted": ["portions","servings","pieces"],
                        "explanation": "The standard advice uses 'portions' or 'servings'.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Mum: Don't eat too many sweets before bed, James. It will hurt your teeth and make it hard to sleep.",
                        "prompt": "What TWO things does eating sweets before bed cause?",
                        "options": [("A","Tooth pain and bad dreams",False),("B","Tooth damage and difficulty sleeping",True),("C","Headache and tiredness",False),("D","Weight gain and headache",False)],
                        "correct": "B",
                        "explanation": "'It will hurt your teeth and make it hard to sleep.'",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Child: Mum, can we have pizza for dinner? Mum: Let's have soup and salad instead - it's healthier.",
                        "prompt": "Why does the mum suggest soup and salad?",
                        "options": [("A","Because she cannot cook pizza",False),("B","Because it is cheaper",False),("C","Because it is healthier",True),("D","Because the child likes salad",False)],
                        "correct": "C",
                        "explanation": "The mum says 'it's healthier.'",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] An orange contains a lot of vitamin ___.",
                        "prompt": "What letter/word completes the sentence?",
                        "correct": "c|C",
                        "accepted": ["c","C"],
                        "explanation": "Oranges are famous for containing Vitamin C.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Teacher: Breakfast is the most important meal of the day. It gives your brain energy to learn.",
                        "prompt": "The teacher says dinner is the most important meal.",
                        "options": [("A","True",False),("B","False",True)],
                        "correct": "B",
                        "explanation": "The teacher says breakfast, not dinner.",
                    },
                    {
                        "qtype": "dictation_sentence",
                        "content": "[Transcript] Drinking water is better than drinking juice.",
                        "prompt": "Listen and write the sentence.",
                        "correct": "Drinking water is better than drinking juice.",
                        "accepted": ["Drinking water is better than drinking juice.", "Drinking water is better than drinking juice"],
                        "explanation": "Comparative sentence with '-er than'.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Announcer: Today's cooking class will teach students how to make a simple fruit salad. You will need bananas, apples, and grapes.",
                        "prompt": "Which fruit is NOT mentioned?",
                        "options": [("A","Bananas",False),("B","Oranges",True),("C","Apples",False),("D","Grapes",False)],
                        "correct": "B",
                        "explanation": "Bananas, apples, and grapes are mentioned - oranges are not.",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] - What do you usually eat for lunch? - I usually eat rice and vegetables and drink water.",
                        "prompt": "What does this person usually drink at lunch?",
                        "correct": "water|Water",
                        "accepted": ["water","Water"],
                        "explanation": "'I ... drink water.'",
                        "match_mode": "multi_accepted",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Talk about your favourite food for 30 seconds. Say what it is and why you like it.",
                        "speaking_topic": "My favourite food: what it is and why I like it.",
                        "instruction": "Use simple sentences and speak for 20-30 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names a food and gives one or more reasons.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What do you usually eat for breakfast?",
                        "speaking_topic": "What I eat for breakfast.",
                        "instruction": "One or two sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names one or more breakfast foods.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Fruit is good for you. Eat an apple or a banana every day. Drink water instead of juice.",
                        "prompt": "Read this health tip aloud.",
                        "speaking_topic": "Read-aloud: healthy eating tips.",
                        "instruction": "Read clearly and naturally.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate reading with clear pronunciation.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Speak using: 1) I eat... for breakfast. 2) I think ... is healthy because... 3) I do not like... .",
                        "speaking_topic": "Guided talk: food habits using three prompts.",
                        "instruction": "Make one sentence for each prompt.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Covers all three prompts in natural spoken English.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "Is it important to eat vegetables every day? Say YES or NO and give one reason.",
                        "speaking_topic": "Should we eat vegetables every day?",
                        "instruction": "Speak for 20 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Clear position and at least one reason.",
                    },
                    {
                        "qtype": "describe_picture",
                        "prompt": "Imagine a picture of a school lunch tray. What healthy foods can you see? Speak for 30 seconds.",
                        "speaking_topic": "Describe a school lunch tray.",
                        "instruction": "Name the foods and say one thing about them.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Names at least two foods and comments on health.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "You should eat more fruit and vegetables.",
                        "prompt": "Listen and repeat.",
                        "speaking_topic": "Repeat: You should eat more fruit and vegetables.",
                        "instruction": "Say the sentence exactly.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate repetition of a health-advice sentence.",
                    },
                    {
                        "qtype": "role_play_response",
                        "prompt": "You are at a restaurant. The waiter asks: 'What would you like to eat?' - Answer politely.",
                        "speaking_topic": "Role-play: ordering food at a restaurant.",
                        "instruction": "Answer as if you are the customer. Use 'I would like...'.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Uses polite request forms (I would like / I'll have).",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Say a sentence using: rice / eat / I / and / fish / for / dinner",
                        "speaking_topic": "Sentence: I eat rice and fish for dinner.",
                        "correct": "I eat rice and fish for dinner.",
                        "accepted": ["I eat rice and fish for dinner.", "I eat rice and fish for dinner"],
                        "match_mode": "normalized",
                        "explanation": "Subject + verb + object + time.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "Compare fruit and vegetables: one thing they have in common and one difference.",
                        "speaking_topic": "Compare fruit and vegetables: one similarity, one difference.",
                        "instruction": "Use 'both' and 'but' or 'however'.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Uses comparison language with one similarity and one difference.",
                    },
                ],
            },
        },  # end A1 beginner

        # ### EXPAND ### - Add A2 through C2 entries here in the same structure.
        # "A2": { 1: {...}, 2: {...}, 3: {...} },

    },  # end beginner

    # =========================================================================
    # TIER: INTERMEDIATE  (Grade 6-7)
    # =========================================================================
    "intermediate": {

        # ---- CEFR A1 --------------------------------------------------------
        "A1": {

            # -- Unit 1: Greetings & Introductions ----------------------------
            1: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "Good morning. My name is Noor Hassan, and I am eleven years old. I recently moved to Kuala Lumpur with my parents and younger brother. In class, I enjoy science and art projects.",
                        "prompt": "Why did Noor introduce her family in the passage?",
                        "options": [("A", "To explain where she lives now", True), ("B", "To describe a science experiment", False), ("C", "To ask for homework help", False), ("D", "To complain about school", False)],
                        "correct": "A",
                        "explanation": "Noor says she moved with her family, so the family detail explains her new situation.",
                    },
                    {
                        "qtype": "true_false",
                        "content": "I am Daniel. I joined Green Valley School last month. At first I was nervous, but my classmates welcomed me warmly.",
                        "prompt": "Daniel felt confident from the very first day.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "Daniel says he was nervous at first, so he was not confident at the beginning.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete the sentence: 'Pleased to ___ you. I am from Cebu.'",
                        "correct": "meet",
                        "accepted": ["meet"],
                        "explanation": "The fixed polite expression is 'Pleased to meet you'.",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "My full name is Lucia Romero. People call me Lucy. I am in Grade 6, and I live near the city library.",
                        "prompt": "What nickname does Lucia use?",
                        "correct": "lucy",
                        "accepted": ["Lucy", "lucy"],
                        "explanation": "The passage clearly says people call Lucia 'Lucy'.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "Hello classmates, my name is Ivan. I like basketball, coding games, and reading adventure stories. I hope we can work together this year.",
                        "prompt": "What is the main idea of Ivan's message?",
                        "options": [("A", "He is inviting everyone to play basketball only", False), ("B", "He is introducing himself and his interests", True), ("C", "He is reviewing an adventure book", False), ("D", "He is announcing a school competition", False)],
                        "correct": "B",
                        "explanation": "Ivan gives his name, hobbies, and a friendly closing, which is a self-introduction.",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "This is my friend Amina. She speaks Arabic and English. Her teacher says she is very helpful.",
                        "prompt": "In the last sentence, who does 'she' refer to?",
                        "correct": "amina|Amina",
                        "accepted": ["Amina", "amina", "my friend Amina"],
                        "explanation": "The pronoun 'she' points back to Amina in the previous sentence.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Hi, I am Ken. I am from Osaka. I enjoy drawing comic characters and practicing the guitar.",
                        "prompt": "Name one activity Ken enjoys.",
                        "correct": "drawing comic characters|practicing the guitar|drawing|guitar",
                        "accepted": ["drawing comic characters", "practicing the guitar", "drawing", "guitar"],
                        "explanation": "Ken says he likes drawing comic characters and practicing guitar.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "sequence_order",
                        "prompt": "Order these actions in a polite first meeting: A) Say your name  B) Greet the person  C) Ask the person's name  D) Say 'Nice to meet you'",
                        "correct": "B, A, C, D",
                        "accepted": ["B A C D", "B, A, C, D", "BACD"],
                        "explanation": "A polite sequence is to greet first, introduce yourself, ask the other person's name, then close politely.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "synonym_match",
                        "prompt": "Choose the word closest in meaning to 'friendly'.",
                        "options": [("A", "kind", True), ("B", "silent", False), ("C", "angry", False), ("D", "late", False)],
                        "correct": "A",
                        "explanation": "'Kind' is closest in meaning to 'friendly' in this context.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "My name is Fatih, and I joined the school debate club. I am still shy, but speaking practice helps me become more confident each week.",
                        "prompt": "What change is Fatih noticing?",
                        "options": [("A", "He stopped attending school", False), ("B", "He is becoming more confident", True), ("C", "He wants to quit debate club", False), ("D", "He changed his name", False)],
                        "correct": "B",
                        "explanation": "Fatih says speaking practice helps him become more confident.",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write one complete sentence introducing yourself with your full name and grade.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong response includes full name and grade in a grammatically correct sentence.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct the sentence: 'She are my new classmate from Brunei.'",
                        "correct": "She is my new classmate from Brunei.",
                        "accepted": ["She is my new classmate from Brunei.", "She is my new classmate from Brunei"],
                        "explanation": "Use 'is' with 'she' and keep the sentence in correct subject-verb agreement.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite as a question: 'You are in Grade 7.'",
                        "correct": "Are you in Grade 7?",
                        "accepted": ["Are you in Grade 7?", "Are you in Grade 7"],
                        "explanation": "For a be-verb question, place 'Are' before the subject.",
                    },
                    {
                        "qtype": "transformation",
                        "prompt": "Complete with the same meaning: 'I come from Jakarta.' -> 'My hometown ___ Jakarta.'",
                        "correct": "is",
                        "accepted": ["is"],
                        "explanation": "'My hometown is Jakarta' keeps the same meaning as the original sentence.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Arrange the words: usually / in / introduce / myself / politely / I / class",
                        "correct": "I usually introduce myself politely in class.",
                        "accepted": ["I usually introduce myself politely in class.", "I usually introduce myself politely in class"],
                        "explanation": "Correct order uses subject + adverb + verb + object + manner + place.",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'Nice to meet you. I hope we ___ good friends.'",
                        "correct": "become|can become|will become",
                        "accepted": ["become", "can become", "will become"],
                        "explanation": "All accepted choices complete the idea naturally and grammatically.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "guided_paragraph",
                        "prompt": "Write 5-6 sentences introducing yourself to a new class. Include: name, age, city, two hobbies, and one learning goal.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete paragraph covers all required points with clear sentence boundaries.",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Do first impressions matter at school? Write 3-4 sentences and give one reason.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The response should state an opinion and support it with a relevant reason.",
                    },
                    {
                        "qtype": "picture_based_prompt",
                        "prompt": "Imagine a picture of two students meeting in class. Write 3 sentences describing what they say and how they feel.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong responses include greeting language and an emotion word.",
                    },
                    {
                        "qtype": "write_letter",
                        "prompt": "Write a short email (5-6 sentences) to a pen friend introducing yourself and asking two questions about their school life.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A good email includes self-introduction, two clear questions, and polite closing language.",
                    },
                ],

                "listening": [
                    {
                        "qtype": "dictation_sentence",
                        "content": "[Transcript] Hello everyone, my name is Hana and I moved here last week.",
                        "prompt": "Write the sentence you hear.",
                        "correct": "Hello everyone, my name is Hana and I moved here last week.",
                        "accepted": ["Hello everyone, my name is Hana and I moved here last week.", "Hello everyone, my name is Hana and I moved here last week"],
                        "explanation": "The dictation sentence includes a greeting, name, and time phrase.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Hi, I am Omar. Could you please tell me where the science lab is?",
                        "prompt": "Why is Omar speaking?",
                        "options": [("A", "To introduce his project", False), ("B", "To ask for directions politely", True), ("C", "To invite someone home", False), ("D", "To order lunch", False)],
                        "correct": "B",
                        "explanation": "Omar politely asks where the science lab is, which is a direction request.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] Girl: I am 12 years old and I enjoy robotics club on Tuesdays.",
                        "prompt": "Which club does the speaker enjoy?",
                        "options": [("A", "Drama club", False), ("B", "Robotics club", True), ("C", "Swimming club", False), ("D", "Music club", False)],
                        "correct": "B",
                        "explanation": "The speaker explicitly says she enjoys robotics club.",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] It is a pleasure to ___ you.",
                        "prompt": "Write the missing word.",
                        "correct": "meet",
                        "accepted": ["meet"],
                        "explanation": "The standard phrase is 'a pleasure to meet you'.",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] Boy: I am from Surabaya, but now I live near the central park with my aunt.",
                        "prompt": "Where does the boy live now?",
                        "correct": "near the central park|near central park|with his aunt near the central park",
                        "accepted": ["near the central park", "near central park", "with his aunt near the central park"],
                        "explanation": "He says he now lives near the central park with his aunt.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] Teacher: Please introduce your partner, not yourself, in this activity.",
                        "prompt": "Students must introduce themselves in this activity.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "The teacher clearly asks students to introduce their partner.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] My name is Paulo. I speak Portuguese at home and English at school.",
                        "prompt": "Where does Paulo speak English?",
                        "options": [("A", "At home", False), ("B", "At school", True), ("C", "At the market", False), ("D", "At the hospital", False)],
                        "correct": "B",
                        "explanation": "Paulo says he speaks English at school.",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] I am happy to join this ___ class.",
                        "prompt": "Write the missing word.",
                        "correct": "new",
                        "accepted": ["new"],
                        "explanation": "The phrase 'join this new class' fits the context and transcript.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] The student says: 'I like reading biographies because real stories inspire me.'",
                        "prompt": "Why does the student like biographies?",
                        "options": [("A", "They are short", False), ("B", "They are funny", False), ("C", "Real stories inspire the student", True), ("D", "They have many pictures", False)],
                        "correct": "C",
                        "explanation": "The student says biographies are inspiring because they are real stories.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Excuse me, I did not catch your name. Could you repeat it slowly, please?",
                        "prompt": "What does the speaker want?",
                        "options": [("A", "To end the conversation", False), ("B", "To hear the name again clearly", True), ("C", "To change classes", False), ("D", "To give directions", False)],
                        "correct": "B",
                        "explanation": "The speaker asks for repetition to understand the name.",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Introduce yourself to a new class in 30-45 seconds. Include your name, where you are from, and one learning goal.",
                        "speaking_topic": "Self-introduction with location and learning goal.",
                        "instruction": "Use complete sentences and at least one connector such as 'and' or 'because'.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong response includes identity details and one clear goal.",
                    },
                    {
                        "qtype": "role_play_response",
                        "prompt": "Role play: You are meeting your class monitor for the first time. Greet them, introduce yourself, and ask one polite question.",
                        "speaking_topic": "First-day meeting with class monitor.",
                        "instruction": "Speak naturally and include one polite question form.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The response should include greeting, self-introduction, and one respectful question.",
                    },
                    {
                        "qtype": "describe_picture",
                        "prompt": "Imagine a picture of students introducing themselves in a circle. Describe what they are doing and how the mood feels.",
                        "speaking_topic": "Describe a classroom introduction activity.",
                        "instruction": "Speak for 30-40 seconds and use at least two descriptive words.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Good answers describe actions and emotions using clear vocabulary.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Good afternoon, everyone. My name is Rina Putri. I enjoy reading mysteries and practicing volleyball after school.",
                        "prompt": "Read the passage aloud.",
                        "speaking_topic": "Read-aloud: extended personal introduction.",
                        "instruction": "Maintain clear pacing and natural pauses.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate pronunciation and pacing show confident oral reading.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "Do you think it is important to learn classmates' names quickly? Give your opinion and one reason.",
                        "speaking_topic": "Opinion on learning classmates' names quickly.",
                        "instruction": "Speak for about 25-35 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete response states a stance and supports it with one relevant reason.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "Compare introducing yourself in person and introducing yourself in an email. Give one similarity and one difference.",
                        "speaking_topic": "Compare face-to-face and email introductions.",
                        "instruction": "Use words like 'both', 'however', or 'but'.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The answer should show comparison language with one clear similarity and one difference.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Use these prompts in order: 1) My name is... 2) I moved from... 3) I want to improve... 4) I hope to...",
                        "speaking_topic": "Guided four-step personal introduction.",
                        "instruction": "Make one complete sentence for each prompt.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong responses include all prompts with coherent sequencing.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What kind of classmate do you want to be this year, and why?",
                        "speaking_topic": "Personal goal for classroom behavior.",
                        "instruction": "Answer in 2-3 sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong answer describes a personal trait and a reason.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "It is nice to meet you, and I look forward to learning together.",
                        "prompt": "Listen and repeat the sentence.",
                        "speaking_topic": "Repeat a polite future-oriented greeting.",
                        "instruction": "Repeat with clear stress on key words.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The sentence should be reproduced accurately with natural rhythm.",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Say a complete sentence using: class / new / my / this / is / first / in / week",
                        "speaking_topic": "Sentence building about first week in new class.",
                        "correct": "This is my first week in this new class.",
                        "accepted": ["This is my first week in this new class.", "This is my first week in this new class"],
                        "match_mode": "normalized",
                        "explanation": "Correct word order creates a meaningful statement about the first week.",
                    },
                ],
            },

            # -- Unit 2: Daily Life & Family ----------------------------------
            2: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "On weekdays, Amira wakes up at 5:45, helps her brother prepare breakfast, and cycles to school by 7:00. In the evening, she reviews her notes and reads for thirty minutes.",
                        "prompt": "Which activity happens before Amira goes to school?",
                        "options": [("A", "Reading for thirty minutes", False), ("B", "Helping her brother prepare breakfast", True), ("C", "Reviewing notes", False), ("D", "Cycling with friends", False)],
                        "correct": "B",
                        "explanation": "The passage states that Amira helps prepare breakfast before leaving for school.",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Rafi's father works in a clinic, and his mother manages a small bakery from home. Their family usually eats dinner together at 7:30 p.m.",
                        "prompt": "Rafi's mother works at a clinic.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "The clinic job belongs to Rafi's father, while his mother manages a bakery.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: My sister ___ her homework before dinner every day.",
                        "correct": "finishes|does",
                        "accepted": ["finishes", "does"],
                        "explanation": "Both verbs can complete the routine sentence correctly in context.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "Every Saturday morning, Leo cleans his room, waters the plants, and then practices piano for one hour.",
                        "prompt": "What does Leo do after watering the plants?",
                        "correct": "practices piano|practices the piano|plays piano",
                        "accepted": ["practices piano", "practices the piano", "plays piano"],
                        "explanation": "The final step listed is practicing piano for one hour.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "The Ibrahim family has a weekly plan for chores. Everyone has responsibilities, and they rotate tasks every month so each person learns different skills.",
                        "prompt": "What is the main idea of the passage?",
                        "options": [("A", "The family dislikes chores", False), ("B", "The family shares chores in an organized way", True), ("C", "The family hires workers", False), ("D", "The family only cleans monthly", False)],
                        "correct": "B",
                        "explanation": "The text focuses on planned and shared household responsibilities.",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Nia's grandfather picks her up from school twice a week because her parents finish work late on those days.",
                        "prompt": "Why does Nia's grandfather pick her up?",
                        "correct": "because her parents finish work late|her parents work late",
                        "accepted": ["because her parents finish work late", "her parents work late"],
                        "explanation": "The passage provides the reason directly: her parents finish work late.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "Marta has a younger cousin. He visits every Sunday, and they build model airplanes together.",
                        "prompt": "What does 'He' refer to?",
                        "correct": "marta's younger cousin|the younger cousin|her cousin",
                        "accepted": ["Marta's younger cousin", "the younger cousin", "her cousin"],
                        "explanation": "The pronoun 'He' points to the younger cousin in the first sentence.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "sequence_order",
                        "prompt": "Order this evening routine: A) Have dinner  B) Pack school bag  C) Finish homework  D) Go to bed",
                        "correct": "C, A, B, D",
                        "accepted": ["C A B D", "C, A, B, D", "CABD"],
                        "explanation": "A realistic sequence is homework, dinner, preparing for next day, then sleep.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "synonym_match",
                        "prompt": "Choose the closest synonym for 'routine'.",
                        "options": [("A", "habit", True), ("B", "surprise", False), ("C", "holiday", False), ("D", "challenge", False)],
                        "correct": "A",
                        "explanation": "In this context, 'routine' means a regular habit.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "Before exams, Huda creates a timetable with short study blocks and breaks. She says this method helps her stay focused.",
                        "prompt": "Why does Huda use a timetable?",
                        "options": [("A", "To avoid all homework", False), ("B", "To stay focused while studying", True), ("C", "To wake up later", False), ("D", "To skip breaks", False)],
                        "correct": "B",
                        "explanation": "The passage explains that the timetable helps her stay focused.",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write one sentence about a weekday responsibility you have at home.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A suitable sentence states a specific routine responsibility clearly.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct the sentence: 'My brother wash the dishes every night.'",
                        "correct": "My brother washes the dishes every night.",
                        "accepted": ["My brother washes the dishes every night.", "My brother washes the dishes every night"],
                        "explanation": "Third-person singular in present simple requires 'washes'.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite using frequency adverb: 'I help my parents. (usually)'",
                        "correct": "I usually help my parents.",
                        "accepted": ["I usually help my parents.", "I usually help my parents"],
                        "explanation": "Place 'usually' before the main verb in this sentence.",
                    },
                    {
                        "qtype": "transformation",
                        "prompt": "Complete with the same meaning: 'She does homework after school.' -> 'After school, homework ___ by her.'",
                        "correct": "is done",
                        "accepted": ["is done"],
                        "explanation": "The passive structure 'is done' preserves meaning at this controlled level.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Arrange the words: weekend / with / grandparents / visit / I / my / every / often",
                        "correct": "I often visit my grandparents every weekend.",
                        "accepted": ["I often visit my grandparents every weekend.", "I often visit my grandparents every weekend"],
                        "explanation": "Correct sentence order communicates frequency and time clearly.",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'When I get home, I first ___ my school uniform and then start homework.'",
                        "correct": "change|change out of",
                        "accepted": ["change", "change out of"],
                        "explanation": "Both accepted answers fit the sentence naturally with routine meaning.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "guided_paragraph",
                        "prompt": "Write 5-6 sentences describing your daily routine from morning to bedtime. Use at least two time connectors.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong paragraph has chronological order and clear connector use.",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Should children help with house chores? Write 3-4 sentences and give one example.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The response should include an opinion and one concrete example.",
                    },
                    {
                        "qtype": "picture_based_prompt",
                        "prompt": "Imagine a picture of a family preparing dinner together. Write 3 sentences about each person's role.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Effective responses name roles and actions with clear sentence structure.",
                    },
                    {
                        "qtype": "write_letter",
                        "prompt": "Write a short message (5-6 sentences) to your cousin explaining your weekday routine and asking about theirs.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete message describes routine details and includes at least one question.",
                    },
                ],

                "listening": [
                    {
                        "qtype": "dictation_sentence",
                        "content": "[Transcript] We usually finish dinner at seven-thirty and review tomorrow's tasks together.",
                        "prompt": "Write the sentence you hear.",
                        "correct": "We usually finish dinner at seven-thirty and review tomorrow's tasks together.",
                        "accepted": ["We usually finish dinner at seven-thirty and review tomorrow's tasks together.", "We usually finish dinner at seven-thirty and review tomorrow's tasks together"],
                        "explanation": "The sentence combines routine time and a family planning action.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] My sister attends piano class on Mondays and Thursdays, while I play badminton on Tuesdays.",
                        "prompt": "Which activity happens on Tuesdays?",
                        "options": [("A", "Piano class", False), ("B", "Badminton", True), ("C", "Swimming", False), ("D", "Art club", False)],
                        "correct": "B",
                        "explanation": "The speaker says they play badminton on Tuesdays.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Could you please set the table while I prepare the soup?",
                        "prompt": "What is the speaker doing?",
                        "options": [("A", "Making a polite request", True), ("B", "Giving weather news", False), ("C", "Inviting someone to travel", False), ("D", "Introducing a classmate", False)],
                        "correct": "A",
                        "explanation": "The phrase 'Could you please...' signals a polite request.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] After school, I rest for twenty minutes, then I complete math homework before dinner.",
                        "prompt": "Which subject is mentioned?",
                        "options": [("A", "Science", False), ("B", "Math", True), ("C", "History", False), ("D", "Geography", False)],
                        "correct": "B",
                        "explanation": "The speaker says they complete math homework.",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] Every evening, my father ___ the plants in our garden.",
                        "prompt": "Write the missing word.",
                        "correct": "waters",
                        "accepted": ["waters"],
                        "explanation": "With 'my father' in present simple, the verb is 'waters'.",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] We divide chores every Sunday so everyone knows their responsibilities for the week.",
                        "prompt": "Why does the family divide chores on Sunday?",
                        "correct": "so everyone knows responsibilities|to know responsibilities for the week",
                        "accepted": ["so everyone knows responsibilities", "to know responsibilities for the week"],
                        "explanation": "The speaker explains this helps everyone know weekly responsibilities.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] On Fridays, my mother picks me up because my club ends late.",
                        "prompt": "The club ends early on Fridays.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "The speaker says the club ends late, not early.",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] My grandparents always give useful ___ when I feel stressed.",
                        "prompt": "Write the missing word.",
                        "correct": "advice",
                        "accepted": ["advice"],
                        "explanation": "The noun 'advice' matches the meaning of helpful guidance.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] I check my school bag every night to make sure I have books, pens, and my assignment notebook.",
                        "prompt": "What is checked every night?",
                        "options": [("A", "Lunch box", False), ("B", "School bag", True), ("C", "Bike", False), ("D", "Uniform shoes", False)],
                        "correct": "B",
                        "explanation": "The speaker clearly states they check their school bag each night.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Let's set a study plan together so we can finish our project on time.",
                        "prompt": "What is the speaker trying to do?",
                        "options": [("A", "Blame a classmate", False), ("B", "Suggest planning cooperation", True), ("C", "Cancel the project", False), ("D", "Change schools", False)],
                        "correct": "B",
                        "explanation": "The speaker suggests working together with a study plan.",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Describe your weekday routine from morning to evening in 40-50 seconds.",
                        "speaking_topic": "Weekday routine timeline.",
                        "instruction": "Include at least four actions and two time expressions.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete response should be chronological and include clear routine details.",
                    },
                    {
                        "qtype": "role_play_response",
                        "prompt": "Role play: Your parent asks you to help with chores while you have homework. Respond politely and suggest a plan.",
                        "speaking_topic": "Balancing chores and homework politely.",
                        "instruction": "Use polite language and propose a sequence of actions.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong responses show respectful tone and practical planning.",
                    },
                    {
                        "qtype": "describe_picture",
                        "prompt": "Imagine a picture of siblings doing different chores at home. Describe who is doing what.",
                        "speaking_topic": "Describe household chore roles in a family scene.",
                        "instruction": "Speak for 30-40 seconds and mention at least three actions.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A quality answer includes people, actions, and clear present tense verbs.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "After school, I rest for a short time, complete my assignments, and help my family prepare dinner before reviewing for the next day.",
                        "prompt": "Read the sentence aloud clearly.",
                        "speaking_topic": "Read-aloud: extended daily routine sentence.",
                        "instruction": "Use natural pauses at commas.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Fluent phrasing and accurate word reading indicate good oral control.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "Should students make a daily study plan? Give your opinion and one example.",
                        "speaking_topic": "Opinion on using daily study plans.",
                        "instruction": "Speak for about 30 seconds.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete response states a view and supports it with an example.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "Compare studying alone and studying with family support. Give one advantage of each.",
                        "speaking_topic": "Compare independent study and family-supported study.",
                        "instruction": "Use comparative language and clear transitions.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong answers present balanced comparison with two distinct advantages.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Use these prompts: 1) After school I... 2) Then I... 3) Before bed I... 4) This helps me...",
                        "speaking_topic": "Guided sequence for after-school routine.",
                        "instruction": "Make four linked sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A coherent response follows all prompts and shows logical sequence.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "Which family routine makes you feel most supported, and why?",
                        "speaking_topic": "Personal reflection on supportive family routines.",
                        "instruction": "Answer in 2-3 connected sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A good response names one routine and provides a personal reason.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "We share responsibilities at home so everyone has time to study and rest.",
                        "prompt": "Listen and repeat the sentence.",
                        "speaking_topic": "Repeat statement about shared responsibilities.",
                        "instruction": "Repeat with clear pronunciation and stress on key words.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate repetition should preserve key meaning words such as responsibilities, study, and rest.",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Say a sentence using: every / table / set / we / dinner / before / the",
                        "speaking_topic": "Build a sentence about pre-dinner chores.",
                        "correct": "We set the table before dinner every day.",
                        "accepted": ["We set the table before dinner every day.", "We set the table before dinner every day"],
                        "match_mode": "normalized",
                        "explanation": "This word order produces a clear and grammatical statement about routine.",
                    },
                ],
            },

            # -- Unit 3: Food & Health ----------------------------------------
            3: {
                "reading": [
                    {
                        "qtype": "multiple_choice",
                        "content": "A balanced lunch often includes whole grains, protein, vegetables, and water. Nutrition teachers recommend this combination because it supports concentration during afternoon classes.",
                        "prompt": "Why is a balanced lunch recommended?",
                        "options": [("A", "It is cheaper than breakfast", False), ("B", "It supports concentration in class", True), ("C", "It removes all homework stress", False), ("D", "It replaces sleep", False)],
                        "correct": "B",
                        "explanation": "The passage says balanced meals help concentration in afternoon classes.",
                    },
                    {
                        "qtype": "true_false",
                        "content": "Tariq reduced sugary drinks and started carrying a water bottle. After two weeks, he felt less tired during sports practice.",
                        "prompt": "Tariq felt more tired after drinking more water.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "The text states he felt less tired, not more tired.",
                    },
                    {
                        "qtype": "fill_in_the_blank",
                        "prompt": "Complete: Doctors advise teenagers to get enough ___ every night.",
                        "correct": "sleep|rest",
                        "accepted": ["sleep", "rest"],
                        "explanation": "Both 'sleep' and 'rest' fit the health recommendation in context.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "detail_scan",
                        "content": "Lina prepares fruit salad with apples, papaya, banana, and yogurt. She avoids extra sugar and keeps portions moderate.",
                        "prompt": "Which ingredient provides dairy in Lina's salad?",
                        "correct": "yogurt|yoghurt",
                        "accepted": ["yogurt", "yoghurt"],
                        "explanation": "Yogurt is the dairy ingredient listed in the salad.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "main_idea",
                        "content": "Health is not only about food. Regular exercise, enough sleep, and stress management are also important. Students can improve well-being by building consistent habits.",
                        "prompt": "What is the main idea?",
                        "options": [("A", "Food is the only factor in health", False), ("B", "Health depends on several consistent habits", True), ("C", "Exercise is unnecessary for students", False), ("D", "Students should avoid all stress", False)],
                        "correct": "B",
                        "explanation": "The passage emphasizes multiple habits together, not food alone.",
                    },
                    {
                        "qtype": "short_answer",
                        "content": "Before exams, Mei changes her routine by sleeping earlier and reducing processed snacks. She says this helps her think more clearly.",
                        "prompt": "What two changes does Mei make before exams?",
                        "correct": "sleeping earlier and reducing processed snacks|sleep earlier and reduce processed snacks",
                        "accepted": ["sleeping earlier and reducing processed snacks", "sleep earlier and reduce processed snacks"],
                        "explanation": "Mei's two changes are earlier sleep and fewer processed snacks.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "reference_question",
                        "content": "Ryan brings homemade lunch to school. It usually includes rice, vegetables, and grilled fish. This helps him avoid too much fried food.",
                        "prompt": "What does 'This' refer to?",
                        "correct": "bringing homemade lunch|his homemade lunch routine|bringing lunch from home",
                        "accepted": ["bringing homemade lunch", "his homemade lunch routine", "bringing lunch from home"],
                        "explanation": "'This' points to Ryan bringing homemade lunch.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "sequence_order",
                        "prompt": "Order these healthy morning actions: A) Drink water  B) Wake up  C) Stretch for five minutes  D) Eat breakfast",
                        "correct": "B, A, C, D",
                        "accepted": ["B A C D", "B, A, C, D", "BACD"],
                        "explanation": "A logical healthy order is waking up, hydrating, moving, then eating.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "synonym_match",
                        "prompt": "Choose the closest synonym for 'nutritious'.",
                        "options": [("A", "healthy", True), ("B", "spicy", False), ("C", "expensive", False), ("D", "frozen", False)],
                        "correct": "A",
                        "explanation": "In food context, 'nutritious' means healthy and beneficial for the body.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "Coach Mira advises her team to drink water before, during, and after training. She explains that hydration improves endurance and recovery.",
                        "prompt": "What is Coach Mira's main recommendation?",
                        "options": [("A", "Skip water during training", False), ("B", "Hydrate throughout training periods", True), ("C", "Only drink sweet beverages", False), ("D", "Avoid recovery routines", False)],
                        "correct": "B",
                        "explanation": "She specifically recommends drinking water before, during, and after training.",
                    },
                ],

                "writing": [
                    {
                        "qtype": "guided_sentence",
                        "prompt": "Write one sentence recommending a healthy snack for school and explain why.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A good sentence names a snack and gives a practical reason.",
                    },
                    {
                        "qtype": "error_correction",
                        "prompt": "Correct the sentence: 'Too much sugar are bad for your teeth.'",
                        "correct": "Too much sugar is bad for your teeth.",
                        "accepted": ["Too much sugar is bad for your teeth.", "Too much sugar is bad for your teeth"],
                        "explanation": "'Sugar' is treated as singular here, so the correct verb is 'is'.",
                    },
                    {
                        "qtype": "sentence_rewrite",
                        "prompt": "Rewrite using 'because': 'I drink more water. I want to stay focused.'",
                        "correct": "I drink more water because I want to stay focused.",
                        "accepted": ["I drink more water because I want to stay focused.", "I drink more water because I want to stay focused"],
                        "explanation": "Using 'because' correctly links action and reason.",
                    },
                    {
                        "qtype": "transformation",
                        "prompt": "Complete with same meaning: 'She avoids junk food.' -> 'Junk food ___ by her.'",
                        "correct": "is avoided",
                        "accepted": ["is avoided"],
                        "explanation": "Passive form 'is avoided' keeps the original meaning.",
                    },
                    {
                        "qtype": "ordering_words",
                        "prompt": "Arrange: every / stretch / minutes / we / for / morning / ten",
                        "correct": "We stretch for ten minutes every morning.",
                        "accepted": ["We stretch for ten minutes every morning.", "We stretch for ten minutes every morning"],
                        "explanation": "Correct word order creates a clear habitual-action sentence.",
                    },
                    {
                        "qtype": "completion",
                        "prompt": "Complete: 'To stay healthy, students should eat more vegetables and ___ sugary drinks.'",
                        "correct": "limit|reduce|avoid",
                        "accepted": ["limit", "reduce", "avoid"],
                        "explanation": "All accepted verbs express reducing unhealthy drink intake.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "guided_paragraph",
                        "prompt": "Write 5-6 sentences about your weekly health routine. Include food, sleep, and exercise habits.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete paragraph should mention all three health dimensions with clear details.",
                    },
                    {
                        "qtype": "opinion_short",
                        "prompt": "Should schools ban sugary drinks? Write 3-4 sentences and include one supporting reason.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong response states a clear position and gives a reason linked to student health.",
                    },
                    {
                        "qtype": "picture_based_prompt",
                        "prompt": "Imagine a picture of students exercising in a park. Write 3 sentences about what they are doing and why it is beneficial.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Effective writing connects observed actions to specific health benefits.",
                    },
                    {
                        "qtype": "write_letter",
                        "prompt": "Write a short letter (5-6 sentences) to a friend giving advice on healthier study-week habits.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete letter includes practical advice and polite supportive tone.",
                    },
                ],

                "listening": [
                    {
                        "qtype": "dictation_sentence",
                        "content": "[Transcript] Drinking water regularly helps your brain stay alert during long lessons.",
                        "prompt": "Write the sentence you hear.",
                        "correct": "Drinking water regularly helps your brain stay alert during long lessons.",
                        "accepted": ["Drinking water regularly helps your brain stay alert during long lessons.", "Drinking water regularly helps your brain stay alert during long lessons"],
                        "explanation": "The sentence links hydration with attention and cognitive readiness.",
                    },
                    {
                        "qtype": "multiple_choice",
                        "content": "[Transcript] Nutrition club meets every Wednesday to discuss healthy lunch ideas and simple recipes.",
                        "prompt": "When does the nutrition club meet?",
                        "options": [("A", "Monday", False), ("B", "Wednesday", True), ("C", "Friday", False), ("D", "Sunday", False)],
                        "correct": "B",
                        "explanation": "The speaker states the meeting happens every Wednesday.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Please pack fruit instead of chips tomorrow so we can compare healthy snack energy levels.",
                        "prompt": "What is the speaker trying to do?",
                        "options": [("A", "Request a healthy choice for an activity", True), ("B", "Cancel tomorrow's class", False), ("C", "Sell fruit in school", False), ("D", "Punish students", False)],
                        "correct": "A",
                        "explanation": "The speaker politely requests fruit for a planned healthy comparison activity.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] I sleep at 9:30 on school nights, and I feel more energetic in morning classes.",
                        "prompt": "What bedtime does the speaker mention?",
                        "options": [("A", "8:30", False), ("B", "9:30", True), ("C", "10:30", False), ("D", "11:30", False)],
                        "correct": "B",
                        "explanation": "The speaker explicitly says 9:30 on school nights.",
                    },
                    {
                        "qtype": "missing_word",
                        "content": "[Transcript] We should wash our hands before eating to stop ___ from spreading.",
                        "prompt": "Write the missing word.",
                        "correct": "germs",
                        "accepted": ["germs"],
                        "explanation": "The common hygiene phrase is 'stop germs from spreading'.",
                    },
                    {
                        "qtype": "short_response",
                        "content": "[Transcript] Coach says we need protein after training so our muscles can recover better.",
                        "prompt": "Why does Coach recommend protein after training?",
                        "correct": "for muscle recovery|so muscles recover better|to recover muscles",
                        "accepted": ["for muscle recovery", "so muscles recover better", "to recover muscles"],
                        "explanation": "The transcript gives recovery as the reason for protein intake.",
                        "match_mode": "multi_accepted",
                    },
                    {
                        "qtype": "true_false",
                        "content": "[Transcript] The school nurse advises students to bring reusable water bottles every day.",
                        "prompt": "The nurse advises students to avoid water bottles.",
                        "options": [("A", "True", False), ("B", "False", True)],
                        "correct": "B",
                        "explanation": "The nurse advises bringing water bottles, not avoiding them.",
                    },
                    {
                        "qtype": "dictation_word",
                        "content": "[Transcript] Eating too fast can affect your ___ and digestion.",
                        "prompt": "Write the missing word.",
                        "correct": "focus",
                        "accepted": ["focus"],
                        "explanation": "The transcript links eating speed with focus and digestion.",
                    },
                    {
                        "qtype": "detail_identification",
                        "content": "[Transcript] For lunch, I choose brown rice, grilled chicken, and steamed vegetables.",
                        "prompt": "Which cooking style is used for the chicken?",
                        "options": [("A", "Fried", False), ("B", "Grilled", True), ("C", "Boiled", False), ("D", "Raw", False)],
                        "correct": "B",
                        "explanation": "The transcript says 'grilled chicken'.",
                    },
                    {
                        "qtype": "speaker_intent",
                        "content": "[Transcript] Let's choose one healthy habit this week and check our progress on Friday.",
                        "prompt": "What is the speaker proposing?",
                        "options": [("A", "A weekly habit challenge", True), ("B", "A food sale", False), ("C", "A holiday trip", False), ("D", "A class cancellation", False)],
                        "correct": "A",
                        "explanation": "The speaker proposes selecting one habit and tracking progress during the week.",
                    },
                ],

                "speaking": [
                    {
                        "qtype": "topic_prompt",
                        "prompt": "Speak for 40-50 seconds about one healthy habit you recently improved and its impact.",
                        "speaking_topic": "Personal healthy-habit improvement story.",
                        "instruction": "Mention what changed, why you changed it, and one result.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong responses include a specific change, purpose, and outcome.",
                    },
                    {
                        "qtype": "role_play_response",
                        "prompt": "Role play: Your friend wants to skip breakfast before an exam. Give polite advice and suggest a better plan.",
                        "speaking_topic": "Advising a friend about exam-day breakfast.",
                        "instruction": "Use persuasive but friendly language.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A quality response gives practical, health-based advice with clear reasoning.",
                    },
                    {
                        "qtype": "describe_picture",
                        "prompt": "Imagine a picture of a school canteen with healthy and unhealthy food choices. Describe what students should choose and why.",
                        "speaking_topic": "Describe healthy choices in a school canteen scene.",
                        "instruction": "Speak for 35-45 seconds and justify two choices.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Good responses identify options and connect choices to health outcomes.",
                    },
                    {
                        "qtype": "read_aloud",
                        "content": "Regular sleep, balanced meals, and daily movement help students maintain concentration, reduce stress, and improve overall academic performance.",
                        "prompt": "Read the sentence aloud.",
                        "speaking_topic": "Read-aloud: integrated health and study-performance statement.",
                        "instruction": "Use clear pronunciation of academic words such as concentration and performance.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Accurate reading of multi-clause sentence shows improved oral fluency.",
                    },
                    {
                        "qtype": "short_opinion",
                        "prompt": "Do you agree that schools should teach nutrition as a separate subject? Explain briefly.",
                        "speaking_topic": "Opinion on nutrition as a school subject.",
                        "instruction": "Give one claim and one supporting reason.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A complete response includes clear position and rationale tied to student life.",
                    },
                    {
                        "qtype": "compare_two_items",
                        "prompt": "Compare home-cooked meals and fast food in terms of nutrition and long-term health.",
                        "speaking_topic": "Compare home-cooked food and fast food.",
                        "instruction": "State one similarity and at least one key difference.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Strong answers balance both items while highlighting nutritional differences.",
                    },
                    {
                        "qtype": "guided_speaking",
                        "prompt": "Use this structure: 1) I used to... 2) Now I... 3) This change helps me...",
                        "speaking_topic": "Habit change using before-and-after structure.",
                        "instruction": "Speak in connected sentences with clear transition markers.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "The response should show contrast between old and new habits with a result.",
                    },
                    {
                        "qtype": "personal_response",
                        "prompt": "What is one health challenge students your age face, and what realistic solution would you suggest?",
                        "speaking_topic": "Student health challenge and practical solution.",
                        "instruction": "Answer in 2-4 sentences.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "A strong response identifies a relevant challenge and offers actionable advice.",
                    },
                    {
                        "qtype": "repeat_sentence",
                        "content": "If we plan our meals and sleep schedule, we can improve both health and school performance.",
                        "prompt": "Listen and repeat.",
                        "speaking_topic": "Repeat sentence connecting planning, health, and performance.",
                        "instruction": "Repeat with clear phrase grouping.",
                        "accepted": [],
                        "match_mode": "ai_graded",
                        "explanation": "Precise repetition preserves both condition and result in the sentence.",
                    },
                    {
                        "qtype": "sentence_building_oral",
                        "prompt": "Say a sentence using: enough / helps / think / us / sleep / clearly",
                        "speaking_topic": "Sentence building about sleep and thinking clearly.",
                        "correct": "Enough sleep helps us think clearly.",
                        "accepted": ["Enough sleep helps us think clearly.", "Enough sleep helps us think clearly"],
                        "match_mode": "normalized",
                        "explanation": "Correct order forms a clear cause-and-effect statement.",
                    },
                ],
            },
        },  # end A1 intermediate

        # ### EXPAND ### - Add A2 through C2 entries for intermediate.
        # "A2": { 1: {...}, 2: {...}, 3: {...} },

    },  # end intermediate

    # ### EXPAND ### - Add advanced tier here.
    # "advanced":     { "A1": {...}, ... },
}


# ---------------------------------------------------------------------------
# DERIVED BANK BUILDERS (centralized, ordered, reusable)
# ---------------------------------------------------------------------------

DERIVATION_PLAN = {
    # Populate levels progressively from A1 baseline for each tier.
    "beginner": ["A2", "B1", "B2", "C1", "C2"],
    "intermediate": ["A2", "B1", "B2", "C1", "C2"],
    "advanced": ["A2", "B1", "B2", "C1", "C2"],
}

LEVEL_COMPLEXITY_NOTE = {
    "A1": "simple personal and familiar contexts",
    "A2": "practical exchanges with clearer details and reasons",
    "B1": "connected ideas, brief reasoning, and contextual precision",
    "B2": "multi-step reasoning, comparison, and clearer abstraction",
    "C1": "nuanced argument, register control, and coherent synthesis",
    "C2": "precise stance, subtle meaning, and advanced discourse flexibility",
}

TIER_RIGOR_NOTE = {
    "beginner": "Use straightforward, concrete language suitable for foundational learners.",
    "intermediate": "Use moderately richer vocabulary and clearer multi-step responses.",
    "advanced": "Use higher precision, stronger reasoning, and more deliberate discourse control.",
}


def _promote_question(tier_code, target_level_code, unit_order, skill_code, qdata):
    """Promote one question to a harder tier/level while preserving schema shape."""
    item = copy.deepcopy(qdata)

    target_topic = SUBLEVEL_TOPICS[target_level_code][unit_order - 1]
    prompt = item.get("prompt", "")
    explanation = item.get("explanation", "")
    level_note = LEVEL_COMPLEXITY_NOTE.get(target_level_code, "clear contextual communication")
    tier_note = TIER_RIGOR_NOTE.get(tier_code, "Use clear and accurate language.")

    if skill_code == "reading":
        item["prompt"] = (
            f"{prompt} Respond for a {target_topic.lower()} context and justify using textual clues."
        )
        if item.get("content"):
            item["content"] = f"{item['content']} Context focus: {target_topic}."
        item["explanation"] = (
            f"{explanation} This fits {target_level_code} because it requires {level_note}."
        ).strip()

    elif skill_code == "writing":
        item["prompt"] = f"{prompt} Keep ideas coherent and relevant to {target_topic.lower()}."
        item["explanation"] = (
            f"{explanation} {tier_note} For {target_level_code}, organize response and add clear support."
        ).strip()
        if item.get("match_mode") == "ai_graded":
            base_instruction = item.get("instruction", "Write in complete, connected sentences.")
            item["instruction"] = f"{base_instruction} Include one specific detail linked to the topic."

    elif skill_code == "listening":
        item["prompt"] = (
            f"{prompt} Focus on practical details and speaker purpose for {target_topic.lower()}."
        )
        if item.get("content"):
            item["content"] = f"{item['content']} Listening context: {target_topic}."
        item["explanation"] = (
            f"{explanation} Correct answers depend on detail selection and context interpretation."
        ).strip()

    elif skill_code == "speaking":
        item["prompt"] = (
            f"{prompt} Include one example relevant to {target_topic.lower()} and one linking expression."
        )
        item["speaking_topic"] = item.get("speaking_topic") or f"{target_topic} speaking prompt"
        base_instruction = item.get("instruction", "Speak clearly and organize your ideas.")
        item["instruction"] = f"{base_instruction} Keep your response relevant to {target_topic}."
        item["explanation"] = (
            f"{explanation} Strong speaking includes relevance, coherence, and clear support."
        ).strip()

    return item


def _build_level_from_previous(tier_code, source_bank, target_level_code):
    target = {}
    for unit_order, skills_data in source_bank.items():
        target[unit_order] = {}
        for skill_code, questions in skills_data.items():
            target[unit_order][skill_code] = [
                _promote_question(tier_code, target_level_code, unit_order, skill_code, qdata)
                for qdata in questions
            ]
    return target


def _ensure_progressive_levels_for_tier(tier_code):
    tier_bank = QUESTION_BANK.get(tier_code)
    if not tier_bank or "A1" not in tier_bank:
        return

    previous_level = "A1"
    for target_level in DERIVATION_PLAN.get(tier_code, []):
        if target_level not in tier_bank:
            tier_bank[target_level] = _build_level_from_previous(
                tier_code=tier_code,
                source_bank=tier_bank[previous_level],
                target_level_code=target_level,
            )
        previous_level = target_level


def _ensure_advanced_a1_baseline():
    """Guarantee advanced A1 exists before deriving higher CEFR levels."""
    if "advanced" in QUESTION_BANK and "A1" in QUESTION_BANK["advanced"]:
        return
    if "intermediate" not in QUESTION_BANK or "A1" not in QUESTION_BANK["intermediate"]:
        return

    QUESTION_BANK.setdefault("advanced", {})
    QUESTION_BANK["advanced"]["A1"] = _build_level_from_previous(
        tier_code="advanced",
        source_bank=QUESTION_BANK["intermediate"]["A1"],
        target_level_code="A1",
    )


# Ensure a clean, predictable bank shape for all currently populated tiers.
_ensure_advanced_a1_baseline()
for _tier in ("beginner", "intermediate", "advanced"):
    _ensure_progressive_levels_for_tier(_tier)


# ---------------------------------------------------------------------------
# MANAGEMENT COMMAND
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed the full hierarchical CEFR question bank (2160 target; A1-Beginner fully populated)."

    QUESTIONS_PER_SKILL = 10
    SERVE_PER_ATTEMPT   = 5   # frontend randomly picks 5 of the 10 per attempt

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding structured CEFR curriculum..."))

        # Validate authored content shape before touching DB rows.
        self._validate_question_bank_structure()

        # Migration-compatibility switches (0003 runs before 0004 on fresh DBs).
        question_columns = {
            c.name for c in connection.introspection.get_table_description(
                connection.cursor(),
                Question._meta.db_table,
            )
        }
        table_names = set(connection.introspection.table_names())
        self._supports_difficulty_tier = (
            DifficultyTier._meta.db_table in table_names and
            'difficulty_tier_id' in question_columns
        )
        self._supports_accepted_answers = 'accepted_answers' in question_columns
        self._supports_speaking_topic = 'speaking_topic' in question_columns
        self._supports_matching_mode = 'answer_matching_mode' in question_columns
        self._supports_case_sensitive = 'is_case_sensitive' in question_columns

        # Migration 0003 runs before 0004 on fresh DBs. In that state, the
        # Question ORM model contains fields that do not yet exist in SQL schema.
        # To prevent migration-time crashes, seed only taxonomy/sublevels here and
        # let full question seeding run again once 0004+ schema is available.
        if not self._supports_accepted_answers:
            level_objs = self._seed_levels()
            self._seed_skills()
            self._seed_question_types()
            self._ensure_all_sublevels(level_objs)
            self.stdout.write(self.style.WARNING(
                "Pre-0004 schema detected. Skipped v2 question bank seeding for migration compatibility."
            ))
            return

        # 1. Core taxonomy
        tier_objs  = self._seed_tiers()
        level_objs = self._seed_levels()
        skill_objs = self._seed_skills()
        qtype_objs = self._seed_question_types()

        # 2. Sublevels, topics, and questions from bank
        total = 0
        for tier_code, levels in QUESTION_BANK.items():
            tier = tier_objs.get(tier_code)
            for level_code, units in levels.items():
                level = level_objs[level_code]
                for unit_order, skills_data in units.items():
                    topic_name = SUBLEVEL_TOPICS[level_code][unit_order - 1]
                    topic    = self._ensure_topic(level, topic_name, unit_order)
                    sublevel = self._ensure_sublevel(level, topic_name, unit_order)
                    for skill_code, questions in skills_data.items():
                        skill = skill_objs[skill_code]
                        for idx, qdata in enumerate(questions, start=1):
                            total += self._seed_question(
                                tier, level, sublevel, skill, topic,
                                qtype_objs, qdata, unit_order, idx,
                            )

        # 3. Ensure skeleton sublevels exist for all levels even if not yet in the bank
        self._ensure_all_sublevels(level_objs)

        total_q = Question.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"Done. Seeded/updated {total} questions this run. Total active questions: {total_q}."
        ))

    # ---- private helpers ---------------------------------------------------

    def _seed_tiers(self):
        if not getattr(self, '_supports_difficulty_tier', False):
            return {}

        objs = {}
        for t in TIERS:
            obj, _ = DifficultyTier.objects.update_or_create(
                code=t["code"],
                defaults={k: v for k, v in t.items() if k != "code"},
            )
            objs[t["code"]] = obj
        return objs

    def _seed_levels(self):
        objs = {}
        for code, name, order, mn, mx in LEVELS:
            obj, _ = CEFRLevel.objects.update_or_create(
                code=code,
                defaults={"name": name, "order": order, "min_score": mn, "max_score": mx},
            )
            objs[code] = obj
        return objs

    def _seed_skills(self):
        objs = {}
        for code, name, order in SKILLS:
            obj, _ = Skill.objects.update_or_create(
                code=code,
                defaults={"name": name, "order": order},
            )
            objs[code] = obj
        return objs

    def _seed_question_types(self):
        objs = {}
        for row in QUESTION_TYPES:
            code, name, fmt, auto, instruction = row
            obj, _ = QuestionType.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "response_format": fmt,
                    "is_auto_gradable": auto,
                    "instruction_template": instruction,
                },
            )
            objs[code] = obj
        return objs

    def _ensure_topic(self, level, topic_name, unit_order):
        from django.utils.text import slugify
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
                "description": f"{level.code} sublevel {unit_order}: {topic_name}",
                "is_active": True,
            },
        )
        return sublevel

    def _ensure_all_sublevels(self, level_objs):
        """Create skeleton sublevels for all levels even if no questions exist yet."""
        for level_code, topics in SUBLEVEL_TOPICS.items():
            level = level_objs[level_code]
            for unit_order, topic_name in enumerate(topics, start=1):
                self._ensure_sublevel(level, topic_name, unit_order)

    def _seed_question(self, tier, level, sublevel, skill, topic, qtype_objs, qdata, unit_order, idx):
        self._validate_single_question_payload(
            tier_code=tier.code if tier else "beginner",
            level_code=level.code,
            unit_order=unit_order,
            skill_code=skill.code,
            qdata=qdata,
        )

        # Keep per-question topic explicit for frontend/export consistency.
        qdata = dict(qdata)
        qdata.setdefault("topic", topic.name)
        if skill.code == "speaking" and not qdata.get("speaking_topic"):
            qdata["speaking_topic"] = qdata["prompt"]

        qtype = qtype_objs.get(qdata["qtype"])
        if not qtype:
            self.stdout.write(self.style.WARNING(f"  Unknown qtype '{qdata['qtype']}' - skipping."))
            return 0

        # Deterministic, human-readable question ID
        tier_prefix = tier.code[:3].upper() if tier else 'GEN'
        qid = f"{tier_prefix}-{level.code}-U{unit_order:02d}-{skill.code[:4].upper()}-{idx:02d}"

        correct_str  = qdata.get("correct", "")
        accepted_raw = list(qdata.get("accepted", []))
        match_mode   = qdata.get("match_mode", "normalized")

        # Auto-populate accepted from pipe-delimited correct string if absent
        if not accepted_raw and correct_str:
            accepted_raw = [a.strip() for a in correct_str.split("|") if a.strip()]

        # AI-graded questions: clear accepted list; engine routes to Gemini
        if match_mode == "ai_graded":
            accepted_raw = []

        defaults = {
            "cefr_level":            level,
            "sublevel":              sublevel,
            "skill":                 skill,
            "question_type":         qtype,
            "topic":                 topic,
            "title":                 f"{sublevel.code} {skill.name} {idx} - {topic.name}",
            "instruction_text":      qdata.get("instruction", ""),
            "content_text":          qdata.get("content", ""),
            "question_text":         qdata["prompt"],
            "correct_answer":        correct_str,
            "sample_answer":         "",    # no longer used; AnswerSample rows are canonical
            "explanation":           qdata.get("explanation", ""),
            "difficulty":            (tier.order if tier else max(1, min(3, (level.order // 2) + 1))),
            "points":               2 if skill.code in ("writing", "speaking") else 1,
            "is_active":             True,
        }

        if self._supports_difficulty_tier:
            defaults["difficulty_tier"] = tier
        if self._supports_accepted_answers:
            defaults["accepted_answers"] = accepted_raw
        if self._supports_speaking_topic:
            defaults["speaking_topic"] = qdata.get("speaking_topic", "")
        if self._supports_matching_mode:
            defaults["answer_matching_mode"] = match_mode
        if self._supports_case_sensitive:
            defaults["is_case_sensitive"] = False

        question, _ = Question.objects.update_or_create(
            question_id=qid,
            defaults=defaults,
        )

        # MCQ / True-False options
        if "options" in qdata:
            question.options.all().delete()
            QuestionOption.objects.bulk_create([
                QuestionOption(
                    question=question,
                    label=opt[0], text=opt[1], is_correct=opt[2], order=i,
                )
                for i, opt in enumerate(qdata["options"])
            ])

        # AnswerSample rows for multi-accepted subjective questions
        if accepted_raw and match_mode == "multi_accepted":
            question.answer_samples.all().delete()
            AnswerSample.objects.bulk_create([
                AnswerSample(
                    question=question,
                    text=ans,
                    keywords=[w.lower() for w in ans.split() if len(w) > 3],
                    order=i,
                )
                for i, ans in enumerate(accepted_raw)
            ])

        return 1

    def _validate_question_bank_structure(self):
        """Validate content structure and pedagogical consistency.

        Rules checked:
          - 10 questions per sublevel+skill
          - required fields exist
          - each question has correct or accepted answers
          - speaking questions always include speaking_topic
          - minimum qtype variety per skill set
          - tier and CEFR codes are known
        """
        for tier_code, levels in QUESTION_BANK.items():
            if tier_code not in TIER_COMPLEXITY_ORDER:
                raise CommandError(f"Unknown tier '{tier_code}' in QUESTION_BANK")

            for level_code, units in levels.items():
                if level_code not in CEFR_COMPLEXITY_GUIDE:
                    raise CommandError(f"Unknown CEFR level '{level_code}' in QUESTION_BANK")

                expected_units = SUBLEVEL_TOPICS.get(level_code, [])
                for unit_order, skills_data in units.items():
                    if unit_order < 1 or unit_order > len(expected_units):
                        raise CommandError(
                            f"Invalid unit_order {unit_order} for {tier_code}/{level_code}; "
                            f"expected 1..{len(expected_units)}"
                        )

                    for skill_code, questions in skills_data.items():
                        if len(questions) != self.QUESTIONS_PER_SKILL:
                            raise CommandError(
                                f"{tier_code}/{level_code}.{unit_order}/{skill_code} has {len(questions)} "
                                f"questions; expected {self.QUESTIONS_PER_SKILL}"
                            )

                        qtypes = set()
                        for qdata in questions:
                            self._validate_single_question_payload(
                                tier_code=tier_code,
                                level_code=level_code,
                                unit_order=unit_order,
                                skill_code=skill_code,
                                qdata=qdata,
                            )
                            qtypes.add(qdata["qtype"])

                        min_variety = SKILL_MIN_VARIETY.get(skill_code, 4)
                        if len(qtypes) < min_variety:
                            raise CommandError(
                                f"{tier_code}/{level_code}.{unit_order}/{skill_code} has {len(qtypes)} unique qtypes; "
                                f"minimum required is {min_variety}"
                            )

    def _validate_single_question_payload(self, tier_code, level_code, unit_order, skill_code, qdata):
        prefix = f"{tier_code}/{level_code}.{unit_order}/{skill_code}"

        for key in REQUIRED_QUESTION_KEYS:
            if key not in qdata or not str(qdata.get(key, "")).strip():
                raise CommandError(f"{prefix}: missing required key '{key}'")

        has_correct = bool(str(qdata.get("correct", "")).strip())
        has_accepted_key = "accepted" in qdata
        if not has_correct and not has_accepted_key:
            raise CommandError(
                f"{prefix}: each question must include 'correct' or 'accepted'"
            )

        if skill_code == "speaking" and not str(qdata.get("speaking_topic", "")).strip():
            raise CommandError(
                f"{prefix}: speaking question missing non-empty 'speaking_topic'"
            )
