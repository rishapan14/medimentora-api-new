# AI-Powered Clinical Report Analysis & Nursing Assistance Platform

Production-ready Flask REST API backend for clinical report analysis, nursing education, simulations, quizzes, and progress tracking.

## Tech Stack

- Python 3.13
- Flask + Blueprint architecture (MVC)
- Flask-SQLAlchemy + MySQL
- Flask-JWT-Extended (access + refresh tokens)
- Flask-CORS
- OpenAI API (report analysis & simulation feedback)
- OCR (pytesseract) + PDF text extraction (pypdf)

## Project Structure

```
flask-student-api/
├── app/
│   ├── __init__.py          # App factory
│   ├── config.py            # Environment configuration
│   ├── constants.py         # Roles, notification types, etc.
│   ├── extensions.py        # db, jwt
│   ├── middleware.py        # Role-based access decorator
│   ├── utils.py             # File upload helpers
│   ├── helpers/
│   │   └── response.py      # Standard {status, message, data} responses
│   ├── models/              # SQLAlchemy models
│   ├── controllers/         # Request handlers (thin layer)
│   ├── services/            # Business logic
│   ├── validations/         # Input validation
│   ├── routes/              # Blueprint route definitions
│   └── seeders/             # Demo data
├── uploads/                 # Report & certificate files
├── run.py
├── run_seeders.py
├── requirements.txt
└── .env.example
```

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# 4. Create MySQL database
mysql -u root -p -e "CREATE DATABASE clinical_platform_db;"

# 5. Run migrations (creates tables) + optional seed data
python run.py
python run_seeders.py
```

### Learning-document background worker

PDF/DOCX/TXT uploads under `/api/medical-teacher/books/upload-and-process` return
HTTP `202` and a durable processing-job identifier. Run one worker alongside the
web API:

```bash
python -m app.learning_worker
```

### Railway MySQL schema bootstrap

Link the API service to the Railway MySQL service and add this API variable:

```text
MYSQL_URL=${{MySQL.MYSQL_URL}}
```

If the database service has a different Railway service name, replace `MySQL`
with that name. `MYSQL_URL` is the only database connection variable; the
database named in that URL is where the application creates all tables. The web
container binds Gunicorn immediately for Railway liveness, then creates and
patches tables in a retrying background thread. Database-backed routes return a
controlled `503 schema_initializing` response until `GET /ready` reports `200`;
`GET /health` remains a database-independent liveness check. Schema failures and
each migration stage are written to the deployment log instead of becoming an
opaque Railway `502`.

Run document processing in a separate Railway worker service with the start
command `python -m app.learning_worker`. Mount
`TEACHER_UPLOAD_FOLDER` (for example, `/data/medical-teacher`) on persistent
storage in production, or set `UPLOAD_FOLDER` to a persistent uploads root.

When `TEACHER_STORAGE_BACKEND=local`, use one container replica. Horizontal
scaling requires a shared/object-storage adapter; the processing services are
already isolated behind the document-storage interface for that extension.

Processing status is available from:

- `GET /api/medical-teacher/jobs`
- `GET /api/medical-teacher/jobs/{job_id}`
- `POST /api/medical-teacher/jobs/{job_id}/retry`

### Grounded document structure (Learning Phase 3)

The background document pipeline now detects explicit modules, chapters,
topics, subtopics, learning objectives, definitions, examples, clinical
concepts, and exam-relevant statements. Detected entries retain document and
page provenance and are stored in the existing `books.structure_json` field.
The detector does not create missing modules or chapters.

- `GET /api/medical-teacher/books/{book_id}/structure`
- `POST /api/medical-teacher/books/{book_id}/detect-structure`

Detected structure remains separate from the persisted Phase 4 course outline described below.

### Personal course generation (Learning Phase 4)

After structure detection, the durable worker creates one private LMS course per
owned source document. Existing `courses` and `course_modules` are reused;
`course_topics` stores the missing topic/subtopic level. Generated records keep
their source node and page provenance, remain private to the uploader, and are
idempotently reused if the same document pipeline is run again.

- `GET /api/medical-teacher/books/{book_id}/course`
- `POST /api/medical-teacher/books/{book_id}/generate-course`

Phase 4 creates the outline only. Lesson content generation begins in Phase 5.

### Grounded lesson generation (Learning Phase 5)

The durable pipeline now creates one cached lesson for every persisted topic or
subtopic. Lessons reuse the existing `lessons` table and retain topic, document,
page, source-hash, generation-method, and structured-content metadata.

By default, lessons organize exact uploaded-document content deterministically.
Set `TEACHER_LESSON_USE_AI=true` to allow optional AI explanations; AI output is
accepted only when every supplied evidence quote exists verbatim in the source.
Unsupported sections remain empty instead of being invented.

- `GET /api/medical-teacher/books/{book_id}/lessons`
- `POST /api/medical-teacher/books/{book_id}/generate-lessons`

Lesson generation is idempotent and cached by topic and document content hash.
Embeddings and semantic retrieval remain Phase 6 work.

### OCR for image reports (required for image upload → extract text)

Image report extraction uses **pytesseract** (Python wrapper) plus the **Tesseract OCR system binary**.
PDF extraction uses **pypdf** only and does not need Tesseract.

This API runs as a **local Flask process** (or in Docker / Railway / Heroku via `Procfile`).
The Next.js frontend does **not** perform OCR — only the Python backend does.

#### Local development

| OS | Install command |
|----|-----------------|
| **Windows** | `winget install --id UB-Mannheim.TesseractOCR` — or `choco install tesseract` — or [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) |
| **macOS** | `brew install tesseract` |
| **Linux (Debian/Ubuntu)** | `sudo apt-get update && sudo apt-get install -y tesseract-ocr` |
| **Linux (Fedora/RHEL)** | `sudo dnf install -y tesseract` |

After installing, **restart the API server** (`python run.py`).

If Tesseract is installed but not on `PATH` (common on Windows), set in `.env`:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Verify installation:

```bash
tesseract --version
```

When Tesseract is missing, `POST /api/reports/<id>/extract` returns HTTP **503** with an `install_hint` field containing OS-specific fix instructions.

#### Docker

The included `Dockerfile` installs Tesseract automatically:

```bash
docker build -t medimentor-api .
docker run -p 5000:5000 --env-file .env medimentor-api
```

#### Heroku / Railway (buildpack + Aptfile)

For buildpack-based deploys, `Aptfile` lists `tesseract-ocr`.
Use a buildpack that supports apt packages (e.g. [heroku-buildpack-apt](https://github.com/heroku/heroku-buildpack-apt)) **before** the Python buildpack.

#### Serverless / Vercel

OCR cannot run on serverless Node/Vercel functions without bundling a large binary.
Deploy this Flask API on a VM, container, or PaaS with apt/root access (Docker, Railway, Render, etc.), or switch to a hosted OCR API (Google Vision, AWS Textract) if you need serverless.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_URL` | Complete MySQL connection URL (required) | — |
| `JWT_SECRET_KEY` | JWT signing key | — |
| `OPENAI_API_KEY` | OpenAI API key | — (uses demo mock if empty) |
| `FRONTEND_URL` | Frontend URL for password reset | `http://localhost:3000` |
| `TESSERACT_CMD` | Full path to Tesseract binary (if not on PATH) | auto-detect |

## API Response Format

Every endpoint returns:

```json
{
  "status": "success | error",
  "message": "Human-readable message",
  "data": { }
}
```

## Authentication

Protected routes require header:

```
Authorization: Bearer <access_token>
```

### Roles

- `admin` — Full access
- `doctor` — Create courses, cases, quizzes, simulations
- `nurse` — Clinical user
- `medical_student` — Default registration role

### Demo Accounts (after seeding)

| Email | Password | Role |
|-------|----------|------|
| admin@clinical.com | admin123 | admin |
| doctor@clinical.com | doctor123 | doctor |
| nurse@clinical.com | nurse123 | nurse |
| student@clinical.com | student123 | medical_student |

## API Endpoints

Base URL: `http://localhost:5000`

### X-Ray OpenAPI / Swagger (Phase 18)

Interactive docs for **AI X-Ray Analysis only** (student + admin monitor/reference):

| URL | Description |
|-----|-------------|
| [`/apidocs`](http://localhost:5000/apidocs) | Swagger UI |
| [`/apispec/xray.yaml`](http://localhost:5000/apispec/xray.yaml) | OpenAPI 3.0 YAML |
| [`/apispec/xray`](http://localhost:5000/apispec/xray) | Spec meta + safety notes (JSON) |

Source file: `docs/openapi-xray.yaml`. Authenticate in Swagger with **Authorize** → Bearer JWT from `POST /api/auth/login`.

**Safety:** X-ray AI is educational / decision-support only — not a diagnosis. Admin evaluation metrics are monitoring proxies, not clinical accuracy.

### AI X-Ray Analysis — `/api/xray` (JWT)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload X-ray image(s) + optional clinical context |
| GET | `/history` | Paginated own history (`date_from` / `date_to`) |
| GET | `/dashboard` | Dashboard summary |
| GET | `/clinical-options` | Clinical form enums |
| POST | `/analyze` | Vision analysis (educational findings) |
| GET/DELETE | `/<id>` | Detail / delete |
| GET | `/<id>/file` | Original image |
| GET | `/<id>/export` | TXT/JSON educational export |
| POST | `/<id>/preprocess` | Preprocess pipeline |
| GET | `/<id>/preprocessed` | Preprocessed image |
| POST | `/<id>/reanalyze` | Re-run analysis |
| POST | `/<id>/explain` | LLM educational explanation |
| POST/GET | `/<id>/heatmap` | Generate / download attention heatmap |
| GET/POST | `/<id>/compare` | Healthy-reference comparison |
| GET | `/<id>/reference` | Selected reference image |
| GET/POST | `/<id>/recommendations` | Learning recommendations |
| GET | `/references*` | Healthy reference library (learner) |
| * | `/admin/references*` | Admin reference library manager |

### Admin X-Ray Monitor — `/api/admin` (JWT + admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/xray-analyses` | Platform-wide X-ray monitor list |
| GET | `/xray-analyses/evaluation-metrics` | Educational model-evaluation metrics |
| GET/DELETE | `/xray-analyses/<id>` | Detail / delete |

### Auth — `/api/auth`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/register` | No | Register user |
| POST | `/login` | No | Login, get tokens |
| POST | `/refresh` | Refresh token | Refresh access token |
| POST | `/forgot-password` | No | Request password reset |
| POST | `/reset-password` | No | Reset password with token |
| GET/PUT | `/profile` | Yes | View/update profile |
| POST | `/logout` | Yes | Logout (client-side token discard) |

### Reports — `/api/reports`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload/pdf` | Upload PDF report (multipart) |
| POST | `/upload/image` | Upload image report (multipart) |
| POST | `/` | Save report metadata |
| GET | `/` | List user reports |
| GET | `/history` | Report history |
| GET | `/<id>` | Get report |
| POST | `/<id>/extract` | Extract text (OCR/PDF) |
| DELETE | `/<id>` | Delete report |

### AI Analysis — `/api/analysis`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Analyze report text via OpenAI |
| GET | `/` | Analysis history |
| GET | `/<id>` | Get analysis |
| DELETE | `/<id>` | Delete analysis |

### Learning — `/api/learning`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/courses` | List courses |
| GET | `/courses/<id>` | Course with lessons |
| POST | `/courses` | Create course (admin/doctor) |
| PUT/DELETE | `/courses/<id>` | Update/delete course |
| GET | `/courses/<id>/lessons` | List lessons |
| POST | `/lessons` | Create lesson |
| POST | `/lessons/<id>/complete` | Mark lesson complete |
| GET | `/bookmarks` | List bookmarks |
| POST/DELETE | `/lessons/<id>/bookmark` | Add/remove bookmark |
| GET | `/recommendations` | Personalized recommendations |
| GET | `/weak-topics` | Weak topic detection |

### Body Systems Learning Hub — `/api/learning` (Phases 2–10, JWT)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/body-systems` | List systems + user progress (`q`, `difficulty`, pagination) |
| GET | `/body-systems/<slug>` | System detail (organs, diseases, courses, quizzes) |
| GET | `/body-systems/<slug>/organs` | Organs in a system |
| GET | `/body-systems/<slug>/diseases` | Diseases in a system |
| POST | `/body-systems/<slug>/start` | Start / resume learning progress |
| GET/PUT | `/body-systems/<slug>/progress` | Get / update hub progress |
| GET | `/organs/<slug>` | Organ detail (`?system=` optional) |
| GET | `/diseases/<slug>` | Disease detail (educational only) |
| GET | `/hub/search?q=` | Search systems, organs, diseases, courses |
| GET | `/hub/explorer` | Interactive body explorer catalog (Phase 5) |
| GET | `/hub/tutor/modes` | AI Tutor mode list (Phase 6) |
| POST | `/hub/tutor` | Context-grounded AI Tutor (Phase 6) |
| GET | `/body-systems/<slug>/quizzes` | Linked hub quizzes + best scores (Phase 7) |
| POST | `/body-systems/<slug>/quizzes/generate` | Auto-generate educational quiz from lesson content (Phase 7) |
| GET | `/hub/flashcards` | Flashcards (`system`, `organ`, `level`, `favorites`) (Phase 8) |
| POST | `/hub/flashcards/generate` | Auto-generate basic/advanced/exam decks (Phase 8) |
| GET | `/hub/flashcards/favorites` | User flashcard favorites (SR-ready) |
| POST/DELETE | `/hub/flashcards/<id>/favorite` | Favorite / unfavorite |
| GET | `/body-systems/<slug>/cases` | Hub clinical cases + disease explorer (`organ`, `disease`) (Phase 9) |
| POST | `/body-systems/<slug>/cases/generate` | Generate educational case simulations (Phase 9) |
| GET | `/hub/recommendations` | Hub recommendations (`source_type`, `source_id`) — report→hub (Phase 10), xray→hub (Phase 11) |
| GET | `/hub/progress` | Hub progress summary — overall %, per-system bars, recently studied (Phase 12) |
| GET | `/hub/certificates` | Educational body-system completion certificates (Phase 13) |
| GET | `/hub/certificates/<id>` | Hub certificate detail (Phase 13) |
| GET | `/hub/certificates/<id>/download` | Download hub certificate PDF (Phase 13) |

Admin (JWT + admin): `/api/admin/learning/body-systems*` — CRUD systems, create/update organs, create diseases, link courses/quizzes. Admin UI: `/admin/body-systems` (Phase 14).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/learning/body-systems` | List systems (`include_inactive`, `q`) |
| POST | `/api/admin/learning/body-systems` | Create system |
| GET | `/api/admin/learning/body-systems/<slug>` | Admin detail (includes unpublished organs/diseases) |
| PUT/PATCH | `/api/admin/learning/body-systems/<slug>` | Update / publish |
| DELETE | `/api/admin/learning/body-systems/<slug>` | Soft-delete (deactivate) |
| POST | `/api/admin/learning/body-systems/<slug>/organs` | Create organ |
| PUT/PATCH | `/api/admin/learning/organs/<organ_slug>` | Update organ |
| POST | `/api/admin/learning/body-systems/<slug>/diseases` | Create disease |
| POST | `/api/admin/learning/body-systems/<slug>/courses` | Link LMS course |
| POST | `/api/admin/learning/body-systems/<slug>/quizzes` | Link LMS quiz |

### Clinical Cases — `/api/clinical-cases`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List/search/filter cases |
| GET | `/<id>` | Get case |
| POST | `/` | Create case (admin/doctor) |
| PUT/DELETE | `/<id>` | Update/delete case |
| POST/DELETE | `/<id>/favorite` | Favorite/unfavorite |

### Simulations — `/api/simulations`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List scenarios |
| GET | `/<id>` | Get scenario |
| POST | `/<id>/submit` | Submit diagnosis & treatment |
| GET | `/history` | Attempt history |

### Quizzes — `/api/quizzes`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List quizzes |
| GET | `/<id>` | Quiz with questions |
| POST | `/<id>/submit` | Submit answers |
| GET | `/results` | My results |
| GET | `/leaderboard` | Leaderboard |

### Progress — `/api/progress`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Learning progress |
| GET | `/dashboard` | Dashboard analytics |
| GET | `/achievements` | Achievements |

### Certificates — `/api/certificates`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/generate` | Generate PDF certificate |
| GET | `/` | List certificates |
| GET | `/<id>/download` | Download PDF |

### Discussions — `/api/discussions`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/` | List/create discussions |
| GET/PUT/DELETE | `/<id>` | CRUD discussion |
| POST | `/<id>/comments` | Add comment/reply |
| POST | `/<id>/like` | Like discussion |

### Notifications — `/api/notifications`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List notifications |
| PUT | `/<id>/read` | Mark as read |
| POST | `/learning-reminder` | Create learning reminder |
| POST | `/quiz-reminder` | Create quiz reminder |

## Example Requests

### Register

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123","full_name":"Jane Doe","role":"medical_student"}'
```

### Login

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"student@clinical.com","password":"student123"}'
```

### Analyze Report

```bash
curl -X POST http://localhost:5000/api/analysis \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"report_text":"Hemoglobin: 10.2 g/dL (low). WBC: 12,000."}'
```

## Production Deployment

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "run:app"
```

Use the included `Procfile` for Heroku/Railway-style deployments.
For Docker, use the included `Dockerfile` (Tesseract is pre-installed).
Ensure Tesseract is available in any non-Docker production environment — see **OCR for image reports** above.

## License

MIT
