# Adaptive CEFR English Speaking Assessment System — Implementation Plan

## Project Overview

Build a Django + PostgreSQL prototype for an **adaptive English language assessment system** based on the CEFR (Common European Framework of Reference for Languages). The system stores CEFR-graded questions across 6 levels (A1–C2) and 4 skill modes, serves them dynamically, and adapts difficulty based on candidate responses.

### Source Document Summary (7 Tabs)

| Tab                    | Content                                                                                                                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All-about-CEFR         | CEFR overview, Thailand/Bangkok applicability, FRELE-TH localization, grade-level mapping, NLP datasets (EFCAMDAT, UniversalCEFR, Write&Improve, CLC-FCE, Ace-CEFR)  |
| Content-for-CEFR-Level | Detailed "can-do" skill descriptors for A1–C2                                                                                                                        |
| CEFR-Course            | Academic course structure per level: task typology (Reception, Production, Interaction, Mediation) and pedagogical means                                             |
| CEFR-Model-Questions   | Full model assessment questions for all 6 levels × 4 modes (24 question sets total) with target descriptors, source links, and complete exam materials               |
| A1-10-Model-Questions  | 40 granular A1 questions (10 per mode: READ-001→010, WRIT-001→010, SPOK-001→010, WMED-001→010) with full metadata (domain, topic, linguistic focus, correct answers) |
| Question-Paper         | Complete A1 exam paper with answer key and official CEFR 2020 descriptor mapping                                                                                     |
| Competitor Analysis    | Cambridge, EF SET, Busuu, Babbel, British Council EnglishScore, Voxy                                                                                                 |

---

## Step 1: Design the Database Schema

### 1.1 Entity-Relationship Overview

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  CEFR_Level   │────<│     Question      │>────│    Skill_Mode      │
└──────────────┘     │                    │     └────────────────────┘
                      │                    │
                      │  ┌────────────────┐│
                      │──│ Question_Meta   ││
                      │  └────────────────┘│
                      │                    │
                      └────────┬───────────┘
                               │
                      ┌────────┴───────────┐
                      │ Candidate_Response  │>────┌──────────────┐
                      └────────────────────┘     │   Candidate   │
                                                  └──────────────┘
```

### 1.2 Table Definitions

#### `cefr_levels`

| Column                  | Type              | Description                                                                                             |
| ----------------------- | ----------------- | ------------------------------------------------------------------------------------------------------- |
| id                      | SERIAL PK         | Auto-increment                                                                                          |
| code                    | VARCHAR(5) UNIQUE | e.g. "A1", "A2", "B1", "B2", "C1", "C2"                                                                 |
| name                    | VARCHAR(100)      | e.g. "Breakthrough", "Waystage", "Threshold", "Vantage", "Effective Operational Proficiency", "Mastery" |
| global_scale_descriptor | TEXT              | The official CEFR global scale "can-do" summary                                                         |
| reception_descriptor    | TEXT              | Key competency for Reception                                                                            |
| production_descriptor   | TEXT              | Key competency for Production                                                                           |
| interaction_descriptor  | TEXT              | Key competency for Interaction                                                                          |
| mediation_descriptor    | TEXT              | Key competency for Mediation                                                                            |
| pedagogical_means       | TEXT              | Action-oriented academic focus description                                                              |
| order                   | INTEGER UNIQUE    | Numeric ordering: 1=A1, 2=A2, 3=B1, 4=B2, 5=C1, 6=C2                                                    |

#### `skill_modes`

| Column   | Type               | Description                                                               |
| -------- | ------------------ | ------------------------------------------------------------------------- |
| id       | SERIAL PK          | Auto-increment                                                            |
| code     | VARCHAR(20) UNIQUE | "reception", "production", "interaction", "mediation"                     |
| name     | VARCHAR(50)        | "Reception", "Production", "Interaction", "Mediation"                     |
| sub_type | VARCHAR(50)        | e.g. "Reading", "Writing", "Spoken", "Written" — the concrete test format |

#### `questions`

| Column               | Type                 | Description                                                     |
| -------------------- | -------------------- | --------------------------------------------------------------- |
| id                   | SERIAL PK            | Auto-increment                                                  |
| item_id              | VARCHAR(30) UNIQUE   | e.g. "A1-READ-001", "A1-WRIT-005"                               |
| cefr_level_id        | FK → cefr_levels     | Links to CEFR level                                             |
| skill_mode_id        | FK → skill_modes     | Links to skill mode                                             |
| target_descriptor    | TEXT                 | The specific CEFR 2020 descriptor this question targets         |
| official_source_link | VARCHAR(500)         | URL to official CEFR documentation                              |
| instructions         | TEXT                 | Instructions shown to the candidate                             |
| stimulus_text        | TEXT                 | The reading passage, notice, email, dialogue, or source content |
| question_text        | TEXT                 | The actual question stem                                        |
| option_a             | TEXT                 | Answer choice A                                                 |
| option_b             | TEXT                 | Answer choice B                                                 |
| option_c             | TEXT                 | Answer choice C                                                 |
| option_d             | TEXT NULL            | Answer choice D (used at B1+ levels)                            |
| correct_answer       | CHAR(1)              | "A", "B", "C", or "D"                                           |
| question_type        | VARCHAR(20)          | "multiple_choice", "open_ended", "roleplay"                     |
| time_allowed_minutes | INTEGER              | Time allocated for this part                                    |
| word_count_min       | INTEGER NULL         | For writing tasks: minimum word count                           |
| word_count_max       | INTEGER NULL         | For writing tasks: maximum word count                           |
| is_active            | BOOLEAN DEFAULT TRUE | Soft-delete / enable flag                                       |
| created_at           | TIMESTAMP            | Auto-set                                                        |

#### `question_metadata`

| Column           | Type                        | Description                                            |
| ---------------- | --------------------------- | ------------------------------------------------------ |
| id               | SERIAL PK                   | Auto-increment                                         |
| question_id      | FK → questions (ONE-TO-ONE) | Links to the question                                  |
| domain           | VARCHAR(50)                 | "Public", "Occupational", "Educational", "Personal"    |
| topic            | VARCHAR(200)                | e.g. "Workplace Communication / Professional Training" |
| linguistic_focus | VARCHAR(300)                | e.g. "Days of the week, basic time expressions"        |

#### `candidates`

| Column                | Type                  | Description                  |
| --------------------- | --------------------- | ---------------------------- |
| id                    | SERIAL PK             | Auto-increment               |
| name                  | VARCHAR(200)          | Full name                    |
| email                 | VARCHAR(200) UNIQUE   | Email                        |
| current_cefr_level_id | FK → cefr_levels NULL | Their assessed/current level |
| created_at            | TIMESTAMP             | Auto-set                     |

#### `candidate_responses`

| Column                | Type            | Description                                 |
| --------------------- | --------------- | ------------------------------------------- |
| id                    | SERIAL PK       | Auto-increment                              |
| candidate_id          | FK → candidates | Who answered                                |
| question_id           | FK → questions  | Which question                              |
| selected_answer       | CHAR(1) NULL    | For MCQ: "A","B","C","D"                    |
| open_response_text    | TEXT NULL       | For open-ended/writing tasks                |
| is_correct            | BOOLEAN         | Whether the answer was correct              |
| response_time_seconds | INTEGER NULL    | How long the candidate took                 |
| session_id            | UUID            | Groups responses into a single test session |
| answered_at           | TIMESTAMP       | When answered                               |

#### `assessment_sessions`

| Column                 | Type                  | Description                    |
| ---------------------- | --------------------- | ------------------------------ |
| id                     | UUID PK               | Session identifier             |
| candidate_id           | FK → candidates       | Who is taking the test         |
| started_at             | TIMESTAMP             | Session start                  |
| ended_at               | TIMESTAMP NULL        | Session end                    |
| starting_cefr_level_id | FK → cefr_levels      | Level the session started at   |
| final_cefr_level_id    | FK → cefr_levels NULL | Determined level after session |
| current_skill_mode_id  | FK → skill_modes NULL | Current mode being tested      |
| total_correct          | INTEGER DEFAULT 0     | Running correct count          |
| total_answered         | INTEGER DEFAULT 0     | Running total count            |

---

## Step 2: Set Up PostgreSQL

### 2.1 Local Setup (Recommended for Prototype)

1. **Install PostgreSQL 16+** from https://www.postgresql.org/download/windows/
   - During install, set superuser password (remember it!)
   - Default port: 5432

2. **Install pgAdmin 4** (bundled with PostgreSQL installer) or **DBeaver** from https://dbeaver.io/download/

3. **Create the project database:**
   ```sql
   CREATE DATABASE adaptive_cefr_db;
   CREATE USER adaptive_user WITH PASSWORD 'your_secure_password';
   ALTER ROLE adaptive_user SET client_encoding TO 'utf8';
   ALTER ROLE adaptive_user SET default_transaction_isolation TO 'read committed';
   ALTER ROLE adaptive_user SET timezone TO 'UTC';
   GRANT ALL PRIVILEGES ON DATABASE adaptive_cefr_db TO adaptive_user;
   ```

### 2.2 Cloud Alternative (Supabase / Neon)

If you prefer cloud, create a free project on:

- **Supabase**: https://supabase.com — gives you a full Postgres instance + REST API
- **Neon**: https://neon.tech — serverless Postgres with generous free tier

Copy the connection string (e.g. `postgresql://user:pass@host:5432/dbname`) for Django settings.

---

## Step 3: Django Project Setup

### 3.1 Create Virtual Environment & Install Dependencies

```powershell
cd C:\Adaptive-Database
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install django psycopg2-binary django-extensions
```

### 3.2 Create Django Project & App

```powershell
django-admin startproject adaptive_cefr .
python manage.py startapp assessment
```

### 3.3 Configure `settings.py`

- Add `'assessment'` and `'django_extensions'` to `INSTALLED_APPS`
- Configure PostgreSQL database:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'adaptive_cefr_db',
        'USER': 'adaptive_user',
        'PASSWORD': 'your_secure_password',
        'HOST': 'localhost',        # or cloud host
        'PORT': '5432',
    }
}
```

### 3.4 Define Django Models (in `assessment/models.py`)

Translate the schema from Step 1 into Django ORM models:

- `CEFRLevel` — 6 rows (A1–C2) with descriptors
- `SkillMode` — 4+ rows (Reception/Reading, Production/Writing, Interaction/Spoken, Mediation/Written)
- `Question` — All test items with FK to level + mode
- `QuestionMetadata` — OneToOne with Question (domain, topic, linguistic focus)
- `Candidate` — Test takers
- `CandidateResponse` — Individual answers
- `AssessmentSession` — Groups responses into adaptive test sessions

### 3.5 Configure Django Admin (in `assessment/admin.py`)

Register all models with customized admin classes:

- List displays with filters by CEFR level, skill mode, domain
- Search fields for item_id, question text
- Inline editing for QuestionMetadata within Question

### 3.6 Run Migrations

```powershell
python manage.py makemigrations assessment
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Access admin at http://127.0.0.1:8000/admin/

---

## Step 4: Populate the Database

### 4.1 Data to Load

Create a Django management command (`assessment/management/commands/seed_data.py`) that programmatically inserts:

**CEFR Levels (6 rows):**
| Code | Name | Order |
|------|------|-------|
| A1 | Breakthrough | 1 |
| A2 | Waystage | 2 |
| B1 | Threshold | 3 |
| B2 | Vantage | 4 |
| C1 | Effective Operational Proficiency | 5 |
| C2 | Mastery | 6 |

Each with full global_scale_descriptor, reception/production/interaction/mediation descriptors, and pedagogical_means from the CEFR-Course tab.

**Skill Modes (8 rows):**
| Code | Name | Sub Type |
|------|------|----------|
| reception_reading | Reception | Reading |
| reception_listening | Reception | Listening |
| production_writing | Production | Writing |
| production_speaking | Production | Speaking |
| interaction_spoken | Interaction | Spoken |
| interaction_written | Interaction | Written |
| mediation_written | Mediation | Written |
| mediation_spoken | Mediation | Spoken |

**Questions — A1 Batch (40 questions from A1-10-Model-Questions tab):**

- A1-READ-001 through A1-READ-010 (10 reading comprehension MCQs)
- A1-WRIT-001 through A1-WRIT-010 (10 writing MCQs)
- A1-SPOK-001 through A1-SPOK-010 (10 spoken interaction MCQs)
- A1-WMED-001 through A1-WMED-010 (10 written mediation MCQs)

Each with full metadata: domain, topic, linguistic focus, correct answer.

**Questions — Model Questions (from CEFR-Model-Questions tab):**

- 24 model questions (6 levels × 4 modes) — these are longer-form assessments with roleplays, extended writing, etc.

**Question Paper:**

- The complete A1 exam paper (4 parts with answer key)

### 4.2 Run the Seed Command

```powershell
python manage.py seed_data
```

---

## Step 5: Build the Adaptive Proof of Concept

### 5.1 Adaptive Logic Engine

The core algorithm (`assessment/adaptive_engine.py`):

```
START at A1 (or a placement level)

FOR each skill mode (Reception → Production → Interaction → Mediation):
    1. SELECT a random question at the current CEFR level for this mode
    2. PRESENT question to candidate
    3. RECORD response (correct/incorrect)
    4. APPLY adaptive rule:
       - If CORRECT: Move UP one CEFR level (A1→A2→B1→B2→C1→C2)
       - If INCORRECT: Move DOWN one level (min A1) or stay
       - After 2 consecutive correct: Confident level-up
       - After 2 consecutive incorrect: Confident level-down
    5. REPEAT until convergence (3 questions at same level) or max questions reached

RESULT: Assessed CEFR level per mode + overall level
```

### 5.2 Implementation Options

**Option A — Django Management Command (Simplest)**
A CLI-based interactive demo:

```powershell
python manage.py run_adaptive_test --candidate-email test@example.com
```

Walks through questions in the terminal, shows adaptive level changes.

**Option B — REST API Endpoint (Recommended for Demo)**
Using Django's built-in views or Django REST Framework:

| Endpoint                           | Method | Description                                |
| ---------------------------------- | ------ | ------------------------------------------ |
| `/api/session/start/`              | POST   | Start new adaptive session for a candidate |
| `/api/session/{id}/next-question/` | GET    | Get next adaptive question                 |
| `/api/session/{id}/answer/`        | POST   | Submit answer, triggers adaptive logic     |
| `/api/session/{id}/result/`        | GET    | Get final assessed CEFR level              |

### 5.3 Demo Presentation Flow

1. **Open Django Admin** → Show organized data: CEFR levels, questions by mode, metadata
2. **Run adaptive test** → Show the engine selecting an A1 question
3. **Simulate correct answer** → Engine queries an A2 question next
4. **Simulate another correct** → Engine moves to B1
5. **Simulate incorrect** → Engine drops back to A2
6. **Show session results** → Final assessed level with response history

---

## Step 6: Project File Structure

```
C:\Adaptive-Database\
├── manage.py
├── requirements.txt
├── adaptive_cefr/                    # Django project settings
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── assessment/                        # Main Django app
│   ├── __init__.py
│   ├── models.py                      # All 7 database models
│   ├── admin.py                       # Admin panel configuration
│   ├── adaptive_engine.py             # Core adaptive logic
│   ├── views.py                       # API views (Step 5B)
│   ├── urls.py                        # App URL routes
│   ├── serializers.py                 # DRF serializers (if using Option B)
│   ├── tests.py                       # Unit tests for adaptive logic
│   ├── management/
│   │   └── commands/
│   │       ├── seed_data.py           # Populate DB from PDF content
│   │       └── run_adaptive_test.py   # CLI demo of adaptive engine
│   └── migrations/
├── Copy-of-Adaptive-Learning.pdf      # Source document
└── pdf_content.txt                    # Extracted text (dev reference)
```

---

## Step 7: Execution Checklist

- [ ] **Step 2**: Install PostgreSQL locally (or set up Supabase/Neon)
- [ ] **Step 2**: Create database `adaptive_cefr_db` and user
- [ ] **Step 3.1**: Create virtual environment, install Django + psycopg2
- [ ] **Step 3.2**: Create Django project (`adaptive_cefr`) and app (`assessment`)
- [ ] **Step 3.3**: Configure `settings.py` with PostgreSQL credentials
- [ ] **Step 3.4**: Write all Django models in `assessment/models.py`
- [ ] **Step 3.5**: Configure Django Admin with filters and inlines
- [ ] **Step 3.6**: Run migrations, create superuser, verify admin panel
- [ ] **Step 4.1**: Write `seed_data.py` management command
- [ ] **Step 4.2**: Run seed command, verify data in admin panel
- [ ] **Step 5.1**: Implement adaptive engine logic
- [ ] **Step 5.2**: Build CLI demo or REST API endpoints
- [ ] **Step 5.3**: Test full adaptive flow end-to-end

---

## Key Design Decisions

| Decision           | Choice                                          | Rationale                                                                      |
| ------------------ | ----------------------------------------------- | ------------------------------------------------------------------------------ |
| Framework          | Django + PostgreSQL                             | Django ORM auto-generates admin panel; PostgreSQL handles relational data well |
| Prototype UI       | Django Admin (no custom HTML/CSS)               | Fastest path to a working, clickable interface                                 |
| Adaptive algorithm | Simple level-up/level-down with streak tracking | Proves the concept without needing IRT (Item Response Theory) complexity       |
| Question format    | Primarily MCQ for prototype                     | Easy to auto-grade; open-ended tasks stored for future NLP scoring             |
| API style          | Django views or DRF                             | Can be upgraded to full REST API later                                         |

---

## Data Volume Summary

| Entity                       | Count                  | Source                                                  |
| ---------------------------- | ---------------------- | ------------------------------------------------------- |
| CEFR Levels                  | 6                      | A1–C2                                                   |
| Skill Modes                  | 8                      | 4 modes × 2 sub-types                                   |
| A1 Granular Questions        | 40                     | A1-10-Model-Questions tab                               |
| Model Questions (all levels) | 24                     | CEFR-Model-Questions tab (6 levels × 4 modes)           |
| A1 Exam Paper                | 4 parts                | Question-Paper tab                                      |
| **Total Questions**          | **~68**                | Ready to seed                                           |
| Candidates                   | 0 (created at runtime) |                                                         |
| Competitors Tracked          | 6                      | Cambridge, EF SET, Busuu, Babbel, British Council, Voxy |
