# Document Translator - Technical Architecture

**Project**: Korean ↔ English Document Translation Service

**LLM**: EXAONE 4.0 (OpenAI API compatible, 64k context)

**Document Types**: PDF, Word (.docx)

**Target Size**: Up to 50MB documents

**Key Constraint**: Preserve exact original formatting

---

## Executive Summary

A production-ready document translation service that handles large Korean-English documents (50MB+, potentially 10-25 million tokens) using a locally-run LLM with limited context window (64k tokens). The system chunks documents intelligently, maintains terminology consistency across 300+ translation units via a rolling glossary, and reconstructs the original formatting precisely.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                  │
│   Web UI (React) ──────────────► API Gateway                           │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼─────────────────────────────────────┐
│                    TRANSLATION API (FastAPI)                            │
│   Jobs ─── Glossaries ─── Auth ─── WebSocket Progress                  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   PostgreSQL    │      │      Redis       │      │  Object Storage  │
│   ───────────   │      │   ───────────    │      │   (S3/MinIO)     │
│   Users, Jobs   │      │   Job Queue      │      │   Documents      │
│   Glossaries    │      │   Progress       │      │   Checkpoints    │
└─────────────────┘      └────────┬─────────┘      └──────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         WORKER POOL (Celery/ARQ)                        │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │              TRANSLATION PIPELINE                                │  │
│   │  Ingest → Chunk → Translate → Reconstruct → Export              │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│                     ┌──────────────────┐                               │
│                     │   EXAONE 4.0     │                               │
│                     │   (Local LLM)    │                               │
│                     └──────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Translation Pipeline

### 2.1 Pipeline Overview

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   INGEST     │───▶│    CHUNK     │───▶│  TRANSLATE   │
│  PDF/Word    │    │  Structure-  │    │  Sequential  │
│  → IR        │    │  Aware Split │    │  + Glossary  │
└──────────────┘    └──────────────┘    └──────────────┘
                                               │
                                               ▼
                    ┌──────────────┐    ┌──────────────┐
                    │    EXPORT    │◀───│ RECONSTRUCT  │
                    │  DOCX/PDF    │    │  IR + Trans  │
                    └──────────────┘    └──────────────┘
```

### 2.2 Document Ingestion

**Strategy**: Convert everything to Word format first, then parse.

**Rationale**:

- PDFs have no semantic structure (just positioned glyphs)
- `pdf2docx` does reasonable layout reconstruction
- Working with one format (docx) simplifies downstream processing
- Word's XML structure preserves fonts, sizes, colors, spacing

```
PDF ──► pdf2docx ──► .docx (temp) ──┐
                                    ├──► python-docx parser ──► IR
Word (.docx) ───────────────────────┘
```

### 2.3 Intermediate Representation (IR)

**Key Insight**: Maintain two parallel structures:

1. **IR** — Full formatting metadata (never sent to LLM)
2. **Translation Units** — Plain text chunks (sent to LLM)

**Core Data Structures**:

| Structure | Purpose | Key Fields |
| --- | --- | --- |
| `TextRun` | Smallest unit - contiguous text with same formatting | text, font_name, font_size, bold, italic, color |
| `Paragraph` | Collection of runs | runs[], style_name, alignment, spacing |
| `TableCell` | Cell containing paragraphs | paragraphs[], row_span, col_span, width |
| `Table` | Grid of cells | cells[][], col_widths[] |
| `Section` | Page layout container | elements[], page dimensions, margins |
| `Document` | Root container | sections[], styles{} |
| `TranslationUnit` | What gets sent to LLM | id, source_text, element_refs[], context_hint |

### 2.4 Chunking Strategy

**Token Budget per LLM Call (64k total)**:

| Component | Tokens | Purpose |
| --- | --- | --- |
| System prompt | ~1,000 | Instructions, formatting rules |
| Rolling glossary | ~3,000 | Terminology consistency |
| Previous unit tail | ~2,000 | Sentence flow continuity |
| Current unit (source) | ~25,000 | Korean text to translate |
| Output buffer | ~30,000 | English tends longer than Korean |
| Safety margin | ~3,000 | Variance buffer |

**Chunking Rules**:

- Never break mid-sentence
- Never break mid-paragraph (preferred)
- Keep tables atomic when possible (split by rows if >20k tokens)
- Target ~25k tokens per unit

### 2.5 Translation Orchestration

**Context Window Composition**:

```
┌──────────────────────────────────────────┐
│ System prompt + instructions (~1k)       │
├──────────────────────────────────────────┤
│ Rolling glossary (~2-4k)                 │
├──────────────────────────────────────────┤
│ Previous TU tail (~2k overlap)           │
├──────────────────────────────────────────┤
│ Current TU content (~25-30k)             │
├──────────────────────────────────────────┤
│ Reserved for output (~25-30k)            │
└──────────────────────────────────────────┘
```

**Orchestration Flow**:

1. For each Translation Unit (sequential):
    - Build prompt with glossary + previous tail + current content
    - Call LLM with retry (max 10 attempts, exponential backoff)
    - Extract glossary terms from response
    - Update rolling glossary
    - Store previous tail for next unit
    - Checkpoint every 10 units

**Retry Strategy**: Exponential backoff, max 60s wait, 10 retries per unit.

### 2.6 Document Reconstruction

**Process**:

1. Build lookup: `element_id → translated_text`
2. Deep copy original IR
3. Walk through and replace text while keeping formatting
4. Handle run distribution (text across multiple formatting runs)

**Text Distribution Strategy**:

- Single run: Simple replace
- Multiple runs: Merge all text into first run's formatting, empty subsequent runs
- (Advanced: Use markup in translation to indicate bold/italic spans)

### 2.7 Export

**DOCX**: Direct write via python-docx with preserved styles

**PDF**: DOCX → PDF via LibreOffice headless conversion

```bash
libreoffice --headless --convert-to pdf --outdir {output_dir} {docx_file}
```

---

## 3. Glossary Management System

### 3.1 The Core Problem

With 300+ chunks translated sequentially:

- **Consistency**: Same term must translate the same way throughout
- **Discovery**: New terms appear mid-document; later chunks need them
- **Context-awareness**: Same Korean word might translate differently in context
- **User control**: Users may want to override/customize terminology

### 3.2 Three-Tier Glossary Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: System Glossaries (Your Predefined)                │
│  • Domain-specific dictionaries you maintain                │
│  • Manufacturing, Legal, Medical, Finance, etc.             │
│  • Lowest priority (overridable)                            │
│  • Shared across all users                                  │
└─────────────────────────────────────────────────────────────┘
                         ▲ inherits + overrides
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: User Glossaries (Per-User)                         │
│  • User uploads their company terminology                   │
│  • Persists across translation jobs                         │
│  • Medium priority                                          │
└─────────────────────────────────────────────────────────────┘
                         ▲ inherits + overrides
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: Job Glossary (Per-Translation-Job)                 │
│  • Extracted terms from current document                    │
│  • User overrides for this specific job                     │
│  • Highest priority                                         │
│  • Can be "promoted" to Tier 2 after job completes          │
└─────────────────────────────────────────────────────────────┘
```

**Priority**: Job > User > System

### 3.3 Glossary Term Data Model

| Field | Type | Description |
| --- | --- | --- |
| id | UUID | Unique identifier |
| source_term | string | Korean term |
| target_term | string | English translation |
| context | string? | "technical", "legal", "general" |
| domain | string? | "manufacturing", "finance", etc. |
| source | enum | EXTRACTED, USER_PROVIDED, SYSTEM_DEFAULT, CONFIRMED |
| confidence | enum | HIGH (3+ occurrences), MEDIUM (1-2), LOW (first occurrence) |
| occurrence_count | int | Times seen in document |
| first_seen_unit | int | Which chunk first encountered this |

### 3.4 Conflict Detection & Resolution

**Conflict**: Same Korean term translated differently by LLM in different chunks.

**Detection**: When adding extracted term, check if existing translation differs.

**Storage**: Conflicts logged with both translations and contexts.

**Resolution**: User manually chooses correct translation via UI; term upgraded to CONFIRMED with HIGH confidence.

### 3.5 Glossary Extraction from LLM

**Prompt Instruction**:

```
When you encounter a technical term, proper noun, or domain-specific phrase:
- First check the glossary below — use the provided translation
- If NOT in glossary and it's a significant term, mark it:
  <glossary>한국어용어|English Translation</glossary>
```

**Extraction**: Regex parse `<glossary>source|target</glossary>` from response, add to job glossary.

### 3.6 Glossary Formatting for Prompt

- Prioritize HIGH confidence terms first
- Sort by occurrence count (most frequent = more important)
- Truncate to fit token budget (~3,000 tokens)
- Format as Markdown table for clarity

---

## 4. Service Architecture

### 4.1 API Endpoints

**Jobs**:

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/v1/jobs` | Create translation job (file upload) |
| GET | `/api/v1/jobs` | List user's jobs |
| GET | `/api/v1/jobs/{id}` | Get job status & progress |
| GET | `/api/v1/jobs/{id}/download` | Download translated document |
| POST | `/api/v1/jobs/{id}/pause` | Pause processing |
| POST | `/api/v1/jobs/{id}/resume` | Resume from checkpoint |
| DELETE | `/api/v1/jobs/{id}` | Cancel job |
| WS | `/api/v1/jobs/{id}/stream` | Real-time progress WebSocket |

**Glossaries**:

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/v1/jobs/{id}/glossary` | Get extracted terms + conflicts |
| POST | `/api/v1/jobs/{id}/glossary/resolve` | Resolve conflict |
| POST | `/api/v1/jobs/{id}/glossary/promote` | Save terms to user glossary |
| GET | `/api/v1/glossaries` | List user glossaries |
| POST | `/api/v1/glossaries` | Create glossary |
| POST | `/api/v1/glossaries/{id}/import` | Bulk import (CSV/Excel) |

**Auth**:

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user |

### 4.2 Database Schema

**Core Tables**:

```
users
├── id (UUID, PK)
├── email (unique)
├── password_hash
├── name
└── created_at

translation_jobs
├── id (UUID, PK)
├── user_id (FK → users)
├── status (pending|processing|paused|completed|failed)
├── source_file_path (S3 path)
├── source_file_name
├── source_file_size_bytes
├── output_file_path (S3 path)
├── total_units
├── completed_units
├── created_at, started_at, completed_at
├── retry_count
├── last_error
└── total_input_tokens, total_output_tokens

job_checkpoints
├── id (UUID, PK)
├── job_id (FK → jobs)
├── unit_index
├── translated_units_json (or S3 reference)
├── glossary_snapshot_json
├── previous_tail
└── created_at

user_glossaries
├── id (UUID, PK)
├── user_id (FK → users)
├── name
├── domain
└── created_at

glossary_terms
├── id (UUID, PK)
├── glossary_id (FK → user_glossaries)
├── source_term
├── target_term
├── context, definition
├── source, confidence
├── occurrence_count
└── created_at, updated_at

job_glossaries
├── id (UUID, PK)
├── job_id (FK → jobs)
├── terms_json
├── conflicts_json
└── updated_at

system_glossaries
├── id (UUID, PK)
├── name, domain
├── terms_json
└── is_active
```

### 4.3 Worker Architecture

**Task Queue**: ARQ (async) or Celery

**Worker Flow**:

1. Receive job from queue
2. Check for checkpoint (resume case)
3. Download source file from S3
4. Run pipeline phases, publishing progress to Redis
5. Checkpoint every 10 units
6. Check for pause request between units
7. Upload output to S3
8. Update job status

**Progress Publishing**: Redis Pub/Sub → WebSocket → Client

**Event Types**:

- `status`: Job status change
- `phase`: Pipeline phase change (ingesting, chunking, translating, etc.)
- `progress`: Unit completion (completed, total, percent, ETA)
- `glossary_update`: New terms extracted
- `paused`: Job paused
- `completed`: Job finished
- `failed`: Job failed with error

### 4.4 Infrastructure (Docker Compose)

| Service | Image | Purpose |
| --- | --- | --- |
| api | Custom | FastAPI application |
| worker | Custom | ARQ workers (scalable replicas) |
| postgres | postgres:15 | Primary database |
| redis | redis:7-alpine | Queue, cache, pub/sub |
| minio | minio/minio | S3-compatible object storage |

---

## 5. Frontend Architecture

### 5.1 Tech Stack

| Technology | Purpose |
| --- | --- |
| React 18 + TypeScript | UI framework |
| Vite | Build tool |
| TanStack Query | Server state management |
| Zustand | Client state (auth, UI) |
| React Router 6 | Routing |
| Tailwind CSS | Styling |
| shadcn/ui | Component library |
| React Hook Form + Zod | Forms & validation |

### 5.2 Project Structure

```
frontend/src/
├── api/                    # API client layer
│   ├── client.ts           # Axios + interceptors
│   ├── auth.ts, jobs.ts, glossaries.ts
│   └── types.ts
├── hooks/                  # Custom hooks
│   ├── useAuth.ts
│   ├── useJobs.ts
│   ├── useJobProgress.ts   # WebSocket hook
│   └── useFileUpload.ts
├── stores/                 # Zustand stores
│   ├── authStore.ts
│   └── uiStore.ts
├── components/
│   ├── ui/                 # shadcn components
│   ├── layout/             # AppLayout, Sidebar, Header
│   ├── auth/               # LoginForm, ProtectedRoute
│   ├── jobs/               # JobList, JobCard, JobProgress, CreateJobDialog
│   └── glossary/           # TermTable, ConflictResolver
└── pages/
    ├── DashboardPage.tsx   # Job list
    ├── JobDetailPage.tsx   # Single job + progress
    └── GlossariesPage.tsx  # Glossary management
```

### 5.3 Key Frontend Patterns

**Auth Flow**:

- JWT stored in Zustand (persisted to localStorage)
- Axios interceptor attaches token to requests
- 401 response triggers token refresh
- Failed refresh → logout + redirect

**Real-time Progress**:

- WebSocket connection per active job
- Receives: phase changes, progress updates, glossary extractions
- Graceful reconnection on disconnect

**Job Status Polling**:

- TanStack Query with `refetchInterval: 10000` for job list
- Faster polling (5s) for job detail page when processing

---

## 6. Authentication

### 6.1 Strategy

- **Registration**: Email + password → bcrypt hash → store
- **Login**: Verify password → issue JWT access token (24h) + refresh token (30d)
- **Token Refresh**: Refresh token → new access + refresh tokens
- **Protection**: All API routes require valid access token (except auth routes)

### 6.2 Token Structure

**Access Token**:

```json
{
  "sub": "user_id",
  "email": "[user@example.com](mailto:user@example.com)",
  "exp": 1234567890,
  "type": "access"
}
```

**Refresh Token**:

```json
{
  "sub": "user_id",
  "exp": 1234567890,
  "type": "refresh"
}
```

### 6.3 WebSocket Auth

WebSockets can't use Authorization header, so token passed as query parameter:

```
ws://host/api/v1/jobs/{id}/stream?token={access_token}
```

---

## 7. Key Design Decisions & Rationale

### 7.1 Why PDF → Word → IR?

| Alternative | Problem |
| --- | --- |
| Direct PDF parsing | PDFs are just positioned glyphs, no semantic structure |
| PDF libraries (PyMuPDF) | Can extract text but loses formatting relationships |
| **pdf2docx → python-docx** | Reconstructs semantic structure, preserves formatting |

### 7.2 Why Sequential Translation (Not Parallel)?

| Approach | Pros | Cons |
| --- | --- | --- |
| Parallel | Faster | Glossary inconsistency, complex merging |
| **Sequential** | Consistent terminology, simpler | Slower |

**Decision**: For quality-focused service, consistency > speed.

### 7.3 Why Three-Tier Glossary?

| Tier | Purpose |
| --- | --- |
| System | Baseline domain knowledge you control |
| User | Company-specific terms that persist |
| Job | Document-specific discoveries |

**Benefit**: Separation of concerns, user control, term promotion workflow.

### 7.4 Why Checkpoint Every 10 Units?

- 50MB doc ≈ 300+ units
- Checkpointing every unit = too much I/O
- Checkpointing every 50 units = too much lost work on failure
- **10 units** = ~3% lost work maximum, reasonable I/O

### 7.5 Why ARQ Over Celery?

| Factor | Celery | ARQ |
| --- | --- | --- |
| Async support | Bolt-on | Native |
| Complexity | Higher | Lower |
| Dependencies | RabbitMQ or Redis | Redis only |
| Python version | Any | 3.7+ |

**Decision**: ARQ for simpler async-native setup. Celery fine if already in stack.

### 7.6 Why MinIO?

- S3-compatible API (easy migration to AWS later)
- Self-hosted (data stays local)
- Handles large files (50MB+) better than DB blobs

---

## 8. Dependencies

### 8.1 Backend

```
# Core
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.0

# Database
asyncpg>=0.29.0
sqlalchemy>=2.0
alembic>=1.13.0

# Queue
arq>=0.25.0

# Storage
boto3>=1.34.0          # S3/MinIO

# Auth
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0

# Translation Pipeline
python-docx>=0.8.11    # Word manipulation
pdf2docx>=0.5.6        # PDF → Word
tiktoken>=0.5.0        # Token counting
openai>=1.0.0          # LLM client

# Utilities
redis>=5.0.0
httpx>=0.26.0
```

### 8.2 Frontend

```
# Core
react@^18.2.0
react-router-dom@^6.22.0
@tanstack/react-query@^5.24.0
zustand@^4.5.0
axios@^1.6.7

# UI
tailwindcss@^3.4.1
lucide-react@^0.330.0
@radix-ui/* (dialog, checkbox, radio-group, progress, toast)

# Forms
react-hook-form@^7.50.1
zod@^3.22.4
react-dropzone@^14.2.3

# Utilities
date-fns@^3.3.1
```

---

## 9. Build Order (Recommended)

| Phase | Tasks |
| --- | --- |
| **1. Core Pipeline** | Ingestion → Chunking → Translation → Reconstruction → Export (standalone script) |
| **2. Glossary** | Manager, extraction, conflict detection |
| **3. Checkpoint** | Save/resume logic |
| **4. Backend API** | Auth + Job CRUD + File upload |
| **5. Worker** | Queue integration, background processing |
| **6. Frontend Shell** | Layout, routing, auth flow |
| **7. Job UI** | List, create, detail pages |
| **8. WebSocket** | Real-time progress |
| **9. Glossary UI** | Conflict resolution, term management |
| **10. Polish** | Error handling, edge cases, loading states |

---

## 10. File Structure (Full Project)

```
doc_translator/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic/
│
├── api/
│   ├── [main.py](http://main.py)
│   ├── routes/
│   │   ├── [jobs.py](http://jobs.py)
│   │   ├── [glossaries.py](http://glossaries.py)
│   │   ├── [auth.py](http://auth.py)
│   │   └── [health.py](http://health.py)
│   ├── middleware/
│   ├── schemas/
│   └── [dependencies.py](http://dependencies.py)
│
├── worker/
│   ├── [main.py](http://main.py)
│   ├── [tasks.py](http://tasks.py)
│   └── [progress.py](http://progress.py)
│
├── core/
│   ├── [config.py](http://config.py)
│   ├── [database.py](http://database.py)
│   ├── [storage.py](http://storage.py)
│   └── [redis.py](http://redis.py)
│
├── translation/
│   ├── ingestion/
│   │   ├── pdf_[converter.py](http://converter.py)
│   │   ├── docx_[parser.py](http://parser.py)
│   │   └── [ir.py](http://ir.py)
│   ├── chunking/
│   │   ├── [tokenizer.py](http://tokenizer.py)
│   │   └── [chunker.py](http://chunker.py)
│   ├── [orchestrator.py](http://orchestrator.py)
│   ├── glossary/
│   │   ├── [manager.py](http://manager.py)
│   │   ├── [extractor.py](http://extractor.py)
│   │   └── [models.py](http://models.py)
│   ├── reconstruction/
│   │   ├── [reconstructor.py](http://reconstructor.py)
│   │   └── text_[distributor.py](http://distributor.py)
│   └── export/
│       ├── docx_[writer.py](http://writer.py)
│       └── pdf_[writer.py](http://writer.py)
│
├── models/
│   ├── [user.py](http://user.py)
│   ├── [job.py](http://job.py)
│   └── [glossary.py](http://glossary.py)
│
└── tests/

frontend/
├── src/
│   ├── api/
│   ├── hooks/
│   ├── stores/
│   ├── components/
│   ├── pages/
│   └── App.tsx
├── package.json
└── vite.config.ts
```

---

## Appendix: Prompt Template

```
You are a professional Korean-to-English translator.

## TRANSLATION RULES
1. Translate ALL Korean text to natural, fluent English
2. Preserve EXACT structure (paragraphs, tables, formatting markers)
3. Use terminology from the provided glossary CONSISTENTLY
4. Match the tone and formality of the original

## TERMINOLOGY HANDLING
When you encounter a technical term not in the glossary:
<glossary>한국어용어|English Translation</glossary>

## OUTPUT FORMAT
- Wrap paragraphs in <p id="X">...</p> matching input IDs
- Wrap table cells in <td id="X">...</td> matching input IDs

## Progress: Unit {current} of {total}

## Glossary:
{formatted_glossary_table}

## Previous context:
{previous_unit_tail}

---

## Source text to translate:
{current_unit_content}

---

Translate the above Korean text to English. Maintain exact structure.
```