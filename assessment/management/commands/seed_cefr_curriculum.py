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

from django.core.management.base import BaseCommand

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

    # ### EXPAND ### - Add intermediate and advanced tiers here.
    # "intermediate": { "A1": {...}, ... },
    # "advanced":     { "A1": {...}, ... },
}


# ---------------------------------------------------------------------------
# MANAGEMENT COMMAND
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed the full hierarchical CEFR question bank (2160 target; A1-Beginner fully populated)."

    QUESTIONS_PER_SKILL = 10
    SERVE_PER_ATTEMPT   = 5   # frontend randomly picks 5 of the 10 per attempt

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding structured CEFR curriculum..."))

        # 1. Core taxonomy
        tier_objs  = self._seed_tiers()
        level_objs = self._seed_levels()
        skill_objs = self._seed_skills()
        qtype_objs = self._seed_question_types()

        # 2. Sublevels, topics, and questions from bank
        total = 0
        for tier_code, levels in QUESTION_BANK.items():
            tier = tier_objs[tier_code]
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
        qtype = qtype_objs.get(qdata["qtype"])
        if not qtype:
            self.stdout.write(self.style.WARNING(f"  Unknown qtype '{qdata['qtype']}' - skipping."))
            return 0

        # Deterministic, human-readable question ID
        qid = (
            f"{tier.code[:3].upper()}-{level.code}-U{unit_order:02d}"
            f"-{skill.code[:4].upper()}-{idx:02d}"
        )

        correct_str  = qdata.get("correct", "")
        accepted_raw = list(qdata.get("accepted", []))
        match_mode   = qdata.get("match_mode", "normalized")

        # Auto-populate accepted from pipe-delimited correct string if absent
        if not accepted_raw and correct_str:
            accepted_raw = [a.strip() for a in correct_str.split("|") if a.strip()]

        # AI-graded questions: clear accepted list; engine routes to Gemini
        if match_mode == "ai_graded":
            accepted_raw = []

        question, _ = Question.objects.update_or_create(
            question_id=qid,
            defaults={
                "difficulty_tier":       tier,
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
                "accepted_answers":      accepted_raw,
                "sample_answer":         "",    # no longer used; AnswerSample rows are canonical
                "explanation":           qdata.get("explanation", ""),
                "speaking_topic":        qdata.get("speaking_topic", ""),
                "answer_matching_mode":  match_mode,
                "is_case_sensitive":     False,
                "difficulty":            max(1, min(3, (level.order // 2) + 1)),
                "points":               2 if skill.code in ("writing", "speaking") else 1,
                "is_active":             True,
            },
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
