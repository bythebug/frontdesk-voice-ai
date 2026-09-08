# Project State

## Last Verified

2026-09-08 (this session — Phases 1–3 complete and committed)

## Project Goal

Build **VoiceOps**: a portfolio-quality, real-time voice AI support agent
for a fictional dental clinic. Browser-based mic in, WebSocket to a FastAPI
backend, local speech-to-text (faster-whisper), local LLM tool-calling
(Ollama) against a real tool registry (appointments, customers, knowledge
base, notifications, escalation) backed by PostgreSQL, local text-to-speech
(Piper) back to the browser. Must run entirely locally at $0 recurring
cost — no paid APIs. Target audience: technical interviewers evaluating a
software/AI engineering resume.

## Requirements

### Confirmed

- Full stack: FastAPI + WebSockets + faster-whisper + Ollama + Piper +
  PostgreSQL (backend); Next.js + TypeScript + React + Tailwind (frontend).
- No paid APIs anywhere (Twilio, ElevenLabs, OpenAI, Anthropic, Deepgram,
  AssemblyAI, etc. all explicitly excluded).
- Real tool calling via an explicit typed tool registry — never arbitrary
  LLM code execution.
- Structured, persisted conversation state (not a stateless prompt loop).
- Real interruption/barge-in handling (documented limitation acceptable if
  perfect real-time isn't achievable locally — but must be a real
  implementation, not faked).
- Appointment booking/cancellation require explicit user confirmation
  before the tool executes.
- Knowledge base uses Postgres full-text search, not a vector DB.
- Redis only if a genuine need appears (currently: no).
- Structured logging with per-conversation timeline (latencies, tool calls,
  errors, interruptions) and a debug view of that timeline.
- Unit + integration + WebSocket tests; don't advance a phase with failing
  tests.
- Docker Compose for at least Postgres; Ollama/Whisper/Piper may run on the
  host.
- 13-phase build process (listed under Remaining Work / Completed below),
  each phase ending in tests+lint+verify+commit.
- Full README covering architecture (Mermaid diagram), setup for every
  local component, example conversation, decisions, limitations, testing.
- Claude should make reasonable engineering decisions autonomously rather
  than asking approval for every small choice; escalate only genuine
  blockers or new-dependency decisions per the global CLAUDE.md policy.

### Assumptions

- Target Ollama model default `llama3.1:8b`, configurable via
  `OLLAMA_MODEL` — chosen as a reasonable modern-Mac default; user can swap
  via `.env`.
- Piper voice default `en_US-lessac-medium` — arbitrary reasonable choice,
  not yet verified to be downloaded/working since Piper isn't installed
  yet.
- `uv` for backend dependency management and `npm` for frontend — matches
  the user's already-installed, per-ecosystem-standard tooling.
- Single-developer, single-machine demo use case — no auth/multi-tenant
  requirements were specified, so none are being built.

### Open Questions

- None blocking right now. Will surface here if a real ambiguity blocks
  Phase 2+ (e.g. exact appointment types/providers to seed the fictional
  clinic with).

## Current Status

**PARTIALLY COMPLETE** — Phases 1–3 of 13 done, verified, and committed.
Phases 4–13 NOT STARTED. Phase 4 is blocked on the user's decision about
installing Ollama + pulling a model (see Blockers/Next Task).

## Completed

### Phase 1 — Repository structure + architecture + development setup

- Initialized git repo at project root.
- Backend scaffold: `backend/` is a `uv`-managed Python 3.12 project
  (`pyproject.toml`) with the fixed package layout (`app/api`, `app/agent`,
  `app/voice`, `app/tools`, `app/db`, `app/services`, `app/core`, `tests/`).
  - `app/core/config.py` — `pydantic-settings`-based `Settings`, env-var
    driven (DB URL, Ollama host/model, Whisper model, Piper voice, etc.).
  - `app/core/logging.py` — stdlib `logging` + custom JSON formatter,
    `configure_logging()` / `get_logger()`.
  - `app/main.py` — FastAPI app factory, CORS for `localhost:3000`,
    lifespan-based logging setup, `GET /health`.
  - Dev deps: pytest, pytest-asyncio, httpx, ruff, mypy.
  - `tests/test_health.py` — verifies `/health` returns 200.
  - Verification: `uv run pytest -q` → 1 passed. `uv run ruff check .` →
    clean. `uv run mypy app` → "Success: no issues found in 11 source
    files."
- Frontend scaffold: `frontend/` created via
  `create-next-app@latest --typescript --tailwind --eslint --app --src-dir`
  (default template, not yet customized for the dashboard — that's Phase
  10). Verification: `npm run build` → compiled successfully, static pages
  generated.
- Root files: `.gitignore` (Python + Node + env + model files),
  `.env.example` (all config knobs the app will use), `docker-compose.yml`
  (Postgres only, with healthcheck — backend/frontend containers deferred
  to Phase 13), `Makefile` (install/dev-backend/dev-frontend/test/lint/
  db-up/db-down), `README.md` (architecture Mermaid diagram, tech stack,
  setup instructions, example conversation, decisions, limitations —
  written to clearly mark what's built vs. planned).
- This session also created project memory: `CLAUDE.md` (project-specific
  hard constraints and stable architecture decisions) and this file.

Committed as `7ce8b5a`.

### Phase 2 — Database + models + migrations

- Installed PostgreSQL 16 natively via Homebrew (`brew install
  postgresql@16`, `brew services start postgresql@16`) — chosen over
  Docker Desktop because Docker Desktop's first-launch privileged-helper
  prompt can't be automated; user confirmed this choice via AskUserQuestion
  this session. Created `voiceops`/`voiceops` role+db and a
  `voiceops_test` db for the test suite.
- `backend/app/db/models.py`: SQLAlchemy 2.0-style (`Mapped`/
  `mapped_column`) models for all 10 tables from the spec plus
  `knowledge_base`. UUID primary keys throughout (Python-side
  `uuid.uuid4`, no Postgres extension needed). Enums
  (`AppointmentStatus`, `ConversationStatus`, `MessageSpeaker`,
  `ToolCallStatus`) as `enum.StrEnum`.
- `backend/app/db/database.py`: async engine/sessionmaker + `get_db()`
  FastAPI dependency.
- Alembic (`backend/migrations/`, async template, `env.py` reads the DB
  URL from `Settings` instead of `alembic.ini` so there's one source of
  truth). Initial migration `14b3c2dbe548_initial_schema.py` creates all
  tables plus a functional GIN index for knowledge-base full-text search
  (`to_tsvector('english', title || ' ' || content)` — raw `op.execute`,
  since SQLAlchemy's ORM metadata can't express a functional index).
  - **Bug found and fixed this session:** Alembic's autogenerated
    `downgrade()` dropped tables but not the Postgres ENUM types those
    tables' columns used, so a downgrade→upgrade round-trip failed with
    `type "conversation_status" already exists`. Fixed by explicitly
    dropping the 4 enum types at the end of `downgrade()`. Verified with
    a full upgrade→downgrade→upgrade cycle against the live local DB.
  - Autogenerate will always propose dropping `knowledge_base_fts_idx`
    (documented in `backend/migrations/README` — expected false positive,
    don't apply it).
- `backend/app/db/repositories.py`: `CustomerRepository`,
  `ProviderRepository`, `AppointmentTypeRepository`,
  `AvailabilityRepository` (includes `try_book()` — an atomic conditional
  `UPDATE ... WHERE is_booked = false` that returns whether the caller won
  the race, preventing double-booking), `AppointmentRepository` (create/
  cancel — cancel frees the slot), `ConversationRepository` (create,
  status, messages, explicit `list_messages()` rather than a lazy-loaded
  relationship — see note below), `ToolCallRepository`,
  `CallSummaryRepository`, `KnowledgeBaseRepository` (Postgres FTS via
  `plainto_tsquery`/`ts_rank`).
  - Note: `Conversation.messages` was originally a lazy-loaded
    relationship but was removed after hitting `MissingGreenlet` errors —
    SQLAlchemy's async lazy-loading only fires cleanly on a fresh query,
    not on an object already in the session's identity map (as happens
    right after `create()`+`flush()` in the same session). Replaced with
    an explicit `ConversationRepository.list_messages()` query. If more
    relationships are added later (Phase 3+), prefer explicit repository
    queries over relying on lazy-loaded async relationships, or use
    `selectinload()`/`AsyncAttrs` deliberately.
- `backend/app/db/seed.py`: idempotent seed for "Willow Creek Dental" — 2
  providers, 5 appointment types, 8 knowledge-base articles (hours,
  services, cancellation policy, insurance, parking, emergency, pricing,
  appointment types), 14 days of 30-minute bookable slots per provider
  (weekdays, 9am–5pm).
- `backend/tests/conftest.py`: session-scoped fixture that creates/drops
  the full schema in `voiceops_test` via `Base.metadata.create_all`
  (not via Alembic — simpler/faster for tests, and the schema is still
  exercised for real by running migrations manually per the README);
  per-test `db_session` fixture that rolls back after each test for
  isolation.
- `backend/tests/test_repositories.py`: 10 tests covering customer
  lookup (found/not-found), availability search, double-booking
  prevention, book+cancel (slot freed on cancel), cancelling a
  nonexistent appointment, conversation state transitions + message
  history, tool-call/summary recording, and KB full-text search.
- Verification: `uv run pytest -q` → 10 passed (against live local
  Postgres, not mocked). `uv run ruff check .` → clean (added
  `extend-exclude = ["migrations/versions"]` since autogenerated Alembic
  files don't follow the same line-length convention). `uv run mypy app`
  → clean (one `# type: ignore[attr-defined]` on `CursorResult.rowcount`,
  which SQLAlchemy's stubs don't expose on the generic `Result` return
  type of `session.execute()` for an `Update` statement — documented
  inline).
- README updated: Postgres setup now documents the native-Homebrew path
  as primary (with Docker as a documented alternative), plus migration/
  seed commands.

Committed as `c69f895`.

### Phase 3 — Appointment/customer/knowledge tools

- `backend/app/agent/tool_registry.py`: generic `ToolRegistry` with a
  `@registry.register(name, description, input_model)` decorator. Each
  handler's own type signature is checked against its specific
  input/output Pydantic models (via `TypeVar`s), with an internal `cast`
  at the point the registry stores it uniformly — works around
  `Callable` parameter contravariance without losing type safety on the
  tool-author-facing side. `execute()` validates arguments, catches
  `ToolExecutionError` (expected, user-facing failures) and any other
  exception (so one broken tool can't crash the conversation), and
  returns a structured `ToolResult(success, data, error, latency_ms)`.
  `schemas()` produces OpenAI/Ollama-compatible function-calling schemas
  for Phase 4.
- 8 tools implemented in `backend/app/tools/`: `lookup_customer`,
  `create_customer` (customers.py — `create_customer` wasn't in the
  spec's example list but is needed for the booking flow to work when a
  patient isn't found); `check_availability`, `book_appointment`,
  `cancel_appointment` (appointments.py — booking/cancelling both require
  an explicit `confirmed: true` input, enforced in the tool itself, not
  just in a future agent prompt; `book_appointment` uses Phase 2's atomic
  `try_book()` so a losing race returns a clear error instead of
  double-booking); `search_knowledge_base` (knowledge.py); `send_confirmation`,
  `transfer_to_human` (notifications.py — simulated, logged, not a fake
  "sent" claim; `transfer_to_human` sets `Conversation.status =
  ESCALATED`).
- Known simplification (documented in `appointments.py`'s module
  docstring): every appointment consumes exactly one 30-minute slot
  regardless of `appointment_type.duration_minutes` — no multi-slot
  allocation for longer procedures.
- 8 new tests in `backend/tests/test_tools.py` (18 total across the
  suite): unknown tool, invalid arguments, not-found cases, full
  check→book→cancel flow, double-booking rejection, confirmation
  enforcement on both book and cancel, re-cancelling an already-cancelled
  appointment, KB search, escalation.
- Verification: `uv run pytest -q` → 18 passed. `uv run ruff check .` →
  clean. `uv run mypy app` → clean (20 source files). Manually verified
  `registry.schemas()` produces valid tool-calling JSON schema for all 8
  tools.

Committed as `61a91c4`.

Phase 1 and Phase 2 are both committed (`7ce8b5a`, `c69f895`).

## In Progress

Nothing mid-flight.

## Next Task

Begin **Phase 4 — Agent engine + structured state + Ollama integration**.
This needs Ollama installed and a model pulled first (multi-GB download —
flagged to the user rather than done unilaterally; see Blockers). Once
Ollama is available:

- `backend/app/agent/state.py`: `ConversationState` (structured, not a
  prompt blob) — conversation_id, customer_id, intent, appointment_date,
  appointment_type, current_step, awaiting_confirmation, etc. Persist the
  parts that matter in Postgres (Phase 2's `conversations`/`messages`
  tables already exist for this).
- `backend/app/agent/prompts.py`: system prompt + prompt-building
  functions. Keep this separate from orchestration logic.
- LLM abstraction (likely `backend/app/agent/llm_provider.py` or similar,
  not explicitly listed in the original suggested tree but needed per the
  spec's `LLMProvider` interface): `generate()` / `generate_structured()`
  over Ollama's HTTP API via `httpx` (no new dependency). Model name from
  `Settings.ollama_model` (already in `core/config.py`) — never
  hardcoded.
- `backend/app/agent/planner.py` / `agent.py`: the actual decision loop —
  conversation state → LLM (with `registry.schemas()` as available
  tools) → tool selection → `registry.execute()` (Phase 3, already
  validates + catches errors) → result → LLM response. Context
  management: don't dump the entire message history into every request
  (per spec) — decide a sensible windowing/summarization strategy.
- Tests: mock the LLM (don't require live Ollama for the test suite) to
  test state transitions, tool-selection flow, and context management in
  isolation — consistent with `CLAUDE.md`'s testing requirements.

## Remaining Work

### Required (per the 13-phase plan)

- Phase 4: Agent engine + structured state + Ollama integration.
- Phase 5: WebSocket communication + documented message protocol.
- Phase 6: Speech-to-text (faster-whisper abstraction).
- Phase 7: Text-to-speech (Piper abstraction).
- Phase 8: Real-time conversation pipeline (wires 4-7 together end to end).
- Phase 9: Interruption/barge-in handling.
- Phase 10: Frontend dashboard (header/status, transcript, voice controls +
  waveform, live agent state, tool activity, call summary).
- Phase 11: Call summaries + observability (structured per-conversation
  timeline, debug page).
- Phase 12: Testing + error handling hardening across all failure modes
  listed in the original spec.
- Phase 13: Docker (containerize backend/frontend) + finalize documentation.

### Desirable / Optional

- Streaming/chunked STT for lower perceived latency (explicitly called out
  as "investigate where practical", not mandatory).
- Nothing else identified yet.

## Architecture

See `README.md` for the diagram and full description. Summary of what
**actually exists** right now (everything else in the README is target
architecture, not yet built):

- `backend/app/main.py`: FastAPI app with CORS + `/health`. No other routes
  yet.
- `backend/app/core/config.py`, `logging.py`: implemented.
- `backend/app/db/`: models, async engine/session, repositories, Alembic
  migrations, seed script — implemented and verified against a live local
  Postgres (see Completed → Phase 2).
- `backend/app/{api,agent,voice,tools,services}/`: empty packages
  (`__init__.py` only), structure only, no logic yet.
- `frontend/`: default Next.js template, unmodified.
- `docker-compose.yml`: Postgres service only (native Homebrew Postgres is
  what's actually running locally right now — see Important Decisions).
- No Ollama integration, no STT/TTS, no WebSocket handler, no tool
  registry, no frontend dashboard yet.

## Important Decisions

- **No Redis for now.** Reason: single backend process, state persists in
  Postgres, no cross-process cache/queue need identified. Status: stable
  until a real need appears.
- **No vector database.** Reason: knowledge base is small and fixed;
  Postgres full-text search is sufficient and keeps the stack simple.
  Status: stable per explicit user instruction.
- **Ollama/Piper/Whisper run on host, not in Docker.** Reason: simplifies
  Apple Silicon (Metal) acceleration and avoids audio device passthrough
  into a container; only Postgres genuinely benefits from containerization
  at this stage. Status: stable, documented in README.
- **`docker-compose.yml` currently only defines Postgres.** Reason: Docker
  isn't installed in this dev environment, so backend/frontend Dockerfiles
  can't be verified yet; writing untested Dockerfiles now would violate the
  "verify before committing" process. Alternatives considered: write full
  compose stack now anyway (rejected — unverifiable, against explicit
  phase-by-phase verification requirement). Status: backend/frontend
  containers explicitly deferred to Phase 13.
- **Postgres runs natively via Homebrew for local dev, not via
  `docker compose up`.** Reason: Docker isn't installed, and Docker
  Desktop's first-launch privileged-helper prompt is a GUI dialog that
  can't be automated/verified non-interactively — user explicitly chose
  the native path when asked (this session). `docker-compose.yml` is kept
  as a documented, equally-valid alternative for anyone who has Docker.
  Status: stable for this environment; revisit if Docker gets installed.
- **Tests use `Base.metadata.create_all` against a real `voiceops_test`
  database, not Alembic migrations.** Reason: faster and simpler for test
  setup/teardown; the migration path is still exercised for real by
  developers following the README (`alembic upgrade head` against
  `voiceops`). Status: stable; revisit only if migration-specific
  behavior (e.g. the raw-SQL FTS index) needs its own test coverage.
- **`uv` for backend, `npm` for frontend.** Reason: both already installed,
  each is that ecosystem's standard lockfile-based tool per the global
  CLAUDE.md preference for existing tooling. Status: stable.

## Dependencies

Backend (`backend/pyproject.toml`):
- `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `websockets` — core
  web/async framework and config.
- Dev: `pytest`, `pytest-asyncio`, `httpx` (FastAPI TestClient), `ruff`
  (lint/format), `mypy` (type check).
- `sqlalchemy[asyncio]`, `asyncpg` — async ORM + Postgres driver.
- `alembic` — schema migrations.
- Not yet added (planned): `faster-whisper` (Phase 6); an Ollama HTTP
  client — likely just `httpx` again, no new dependency (Phase 4); Piper
  is invoked as a local process/binary or via the `piper-tts` pip package
  (Phase 7, decision TBD).

Frontend (`frontend/package.json`): default `create-next-app` deps
(`next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `eslint`,
`eslint-config-next`). Nothing added yet beyond the template.

## Commands

Verified this session:

```bash
cd backend && uv sync                          # installs backend deps
cd backend && uv run pytest -q                 # 10 passed (needs voiceops_test db)
cd backend && uv run ruff check .              # clean
cd backend && uv run mypy app                  # clean
cd backend && uv run alembic upgrade head      # applies schema to `voiceops` db
cd backend && uv run alembic downgrade -1      # verified full round-trip
cd backend && uv run python -m app.db.seed     # idempotent seed, verified
cd backend && uv run uvicorn app.main:app --reload --port 8000  # not yet run as a live server, but wired correctly (health test uses TestClient against the same app)
cd frontend && npm install                     # succeeded during create-next-app
cd frontend && npm run build                   # compiled successfully
brew services start postgresql@16              # native Postgres, verified running
```

From repo root (Makefile, `db-up`/`db-down` now target `brew services`, not
yet exercised via `make` directly but mirror the verified commands above):
`make install`, `make dev-backend`, `make dev-frontend`, `make test`,
`make lint`, `make db-up`, `make db-down`.

Not verified: `docker compose up -d postgres` (Docker not installed in this
environment — REQUIRES VERIFICATION if/when Docker is available; not the
active local-dev path).

## Verification

- 2026-09-08: `uv run pytest -q` in `backend/` → `1 passed`.
- 2026-09-08: `uv run ruff check .` in `backend/` → no errors (after fixing
  one line-length violation in `logging.py`).
- 2026-09-08: `uv run mypy app` in `backend/` → "Success: no issues found
  in 11 source files."
- 2026-09-08: `npm run build` in `frontend/` → "Compiled successfully",
  static pages generated for `/` and `/_not-found`.
- 2026-09-08: `uv run pytest -q` (Phase 2, repositories) → 10 passed
  against a live local `voiceops_test` Postgres database.
- 2026-09-08: `uv run alembic upgrade head` → `uv run alembic downgrade
  -1` → `uv run alembic upgrade head` round-trip against live local
  `voiceops` database → succeeded after fixing the enum-type-drop bug
  (see Completed → Phase 2).
- 2026-09-08: `uv run python -m app.db.seed` → seeded successfully;
  re-run confirmed idempotent (prints "Already seeded — skipping.").
- 2026-09-08: manually inspected DB with `psql` — confirmed all 10 tables
  and the `knowledge_base_fts_idx` GIN index exist after migration.
- Not verified: actual browser load of the frontend dev server; actual
  `uvicorn` server start (only the FastAPI app object was tested, via
  `TestClient`).

## Known Issues

- Docker, Ollama, and Piper are **not installed** in this dev environment.
  Nothing from Phase 4 (Ollama) or Phase 7 (Piper) onward can be
  end-to-end verified until they are. Postgres (Phase 2) no longer
  depends on Docker — it's installed natively via Homebrew.
- System `python3` is 3.9.6 (too old for this project) — irrelevant in
  practice since `uv` manages its own 3.12+ interpreter for the backend,
  but worth knowing if anyone runs backend code outside `uv run`.
- No `piper` Homebrew formula exists; Piper must be installed via
  `pip install piper-tts` or a downloaded release binary (documented in
  README).
- `alembic revision --autogenerate` will always propose dropping
  `knowledge_base_fts_idx` (a raw-SQL functional index invisible to ORM
  metadata) — expected, documented in `backend/migrations/README`, do not
  apply that line if it appears in a future autogenerated migration.

## Blockers

**Phase 4 is blocked pending a user decision on Ollama.** Ollama isn't
installed. Installing it (`brew install ollama`) is low-risk/reversible,
but pulling a model (`ollama pull <model>`) is a multi-GB download and
the right model choice depends on the user's machine (RAM/disk) — this
session paused rather than picking a model and downloading it
unilaterally. Ask the user: install Ollama + which model (e.g.
`llama3.1:8b` ~4.9GB, or a smaller one), or do they already have Ollama
set up elsewhere. Phase 7 will need Piper installed too — not yet asked
about, lower priority than Phase 4.

## Files and Components

| Path | Purpose | State |
|---|---|---|
| `backend/app/main.py` | FastAPI app entrypoint | Implemented (`/health` only) |
| `backend/app/core/config.py` | Settings/env config | Implemented |
| `backend/app/core/logging.py` | Structured JSON logging | Implemented |
| `backend/app/db/models.py` | SQLAlchemy models, all 10 tables | Implemented, verified |
| `backend/app/db/database.py` | Async engine/session + FastAPI dep | Implemented |
| `backend/app/db/repositories.py` | Data-access layer for all entities | Implemented, tested |
| `backend/app/db/seed.py` | Fictional clinic seed data | Implemented, verified, idempotent |
| `backend/migrations/` | Alembic async migrations | Implemented, round-trip verified |
| `backend/app/agent/tool_registry.py` | Typed tool registry + execution | Implemented, tested |
| `backend/app/tools/` | 8 tool implementations | Implemented, tested |
| `backend/app/{api,agent/state.py,agent/prompts.py,agent/planner.py,agent/agent.py,voice,services}/` | Fixed layout for Phase 4+ | Structure only |
| `backend/tests/test_health.py` | Health endpoint test | Implemented, passing |
| `backend/tests/test_repositories.py` | Repository layer tests (10) | Implemented, passing |
| `backend/tests/test_tools.py` | Tool layer tests (8) | Implemented, passing |
| `backend/tests/conftest.py` | Test DB fixtures | Implemented |
| `frontend/` | Next.js dashboard | Default template only |
| `docker-compose.yml` | Local Postgres (alt. to native Homebrew) | Implemented, unverified (no Docker) |
| `Makefile` | Dev command shortcuts | Implemented, `db-up`/`db-down` target `brew services` |
| `README.md` | Setup + architecture docs | Written, marks planned vs. built |
| `CLAUDE.md` | Project-specific hard constraints | Implemented |

## Session Progress

### 2026-09-08 — Session 1: Project creation, Phase 1

- What changed: Created the entire repository from an empty directory.
  Initialized git. Scaffolded backend (`uv` + FastAPI + core config/logging
  + health endpoint + tests) and frontend (Next.js/TS/Tailwind default
  template). Wrote root dev-experience files (`.gitignore`, `.env.example`,
  `docker-compose.yml`, `Makefile`, `README.md`) and project memory
  (`CLAUDE.md`, `PROJECT.md`).
- Why: User's `/init-project` command carried the full VoiceOps spec and
  explicitly instructed starting Phase 1 immediately after environment
  inspection.
- Verification: see Verification section above — backend tests/lint/type
  checks pass, frontend builds cleanly.
- Remaining: everything in Remaining Work above. Immediate next step is
  Phase 3 (typed tool registry + tool implementations).

### 2026-09-08 — Session 1 (cont'd): Phase 2

- What changed: Installed PostgreSQL 16 natively via Homebrew (user chose
  this over Docker Desktop when asked — see Important Decisions). Built
  the full DB layer: SQLAlchemy models for all 10 tables, async engine/
  session, Alembic migrations (fixed a real enum-type-drop bug in the
  autogenerated downgrade), a repository layer covering every operation
  Phase 3's tools will need (including atomic double-booking prevention),
  seed data for the fictional clinic, and 10 passing repository tests
  against a live Postgres test database.
- Why: Natural continuation of the `/init-project` command's instruction
  to begin Phase 1 and keep moving through the phased plan without
  stopping for approval on each small decision; paused only for the one
  genuine environment fork (Docker vs. native Postgres) that needed the
  user's input.
- Verification: see Verification section above — 10 tests passing against
  real Postgres, ruff/mypy clean, migration round-trip (upgrade→downgrade→
  upgrade) verified live, seed idempotency verified.
- Remaining: everything in Remaining Work above. Phase 3 is next.

### 2026-09-08 — Session 1 (cont'd): Phase 3

- What changed: Built the typed tool registry and all 8 tools (customer
  lookup/creation, availability/booking/cancellation, KB search,
  confirmation/escalation), each with Pydantic validation, structured
  results, and error handling that can't crash the conversation. Solved
  a real mypy variance issue in the registry's generic decorator. Added
  8 tests (18 total in the suite).
- Why: Continuation of the phased build; this phase needed no new
  environment decisions (built entirely on Phase 2's repositories).
- Verification: 18/18 tests passing against live Postgres, ruff/mypy
  clean, manually confirmed `registry.schemas()` output is valid
  tool-calling JSON schema.
- Remaining: everything in Remaining Work above. Paused here — Phase 4
  needs an Ollama install + model pull decision from the user before
  proceeding (see Blockers).

## Handoff Notes

1. **What are we building?** VoiceOps — a local-only, real-time voice AI
   support agent (FastAPI/WebSocket/faster-whisper/Ollama/Piper/Postgres
   backend, Next.js frontend) for a fictional dental clinic, built as a
   13-phase portfolio project. Full spec is in the original user request;
   the durable constraints/decisions distilled from it live in `CLAUDE.md`
   and this file's Requirements/Important Decisions sections.
2. **Where are we now?** Phases 1–3 are done, verified, and committed
   (`7ce8b5a`, `c69f895`, `61a91c4`) as of the end of this session (check
   `git log`/`git status` to confirm current state — don't trust this
   line blindly if time has passed).
3. **What was most recently completed?** Phase 3: typed tool registry +
   8 tools (customer lookup/create, availability/booking/cancellation,
   KB search, confirmation/escalation), 18 passing tests total.
4. **What remains?** Phases 4–13, in order — see Remaining Work. Phase 4
   (agent engine + Ollama) is next; the Next Task section above has
   specifics.
5. **What should happen next?** Phase 4 needs Ollama installed
   (`brew install ollama`) and a model pulled (`ollama pull <model>` —
   multi-GB download). This session deliberately paused instead of
   picking a model and downloading it unilaterally — ask the user which
   model / confirm before installing, then implement Phase 4. Piper is
   needed before Phase 7 — flag if still missing when that phase starts.
6. **What must the next Claude be careful about?**
   - Don't re-scaffold what already exists — check `git log` and this file
     first. The DB layer, repositories, seed data, and tool registry are
     done; Phase 4's agent should call `registry.execute()` and the
     Phase 2 repositories, not reimplement either.
   - Don't mark a phase complete without actually running its
     tests/lint/verification (see `CLAUDE.md` Required Commands) — this
     session caught a real migration bug (orphaned enum types on
     downgrade) precisely by actually running the round-trip instead of
     assuming autogenerate was correct.
   - Don't add Redis, a vector DB, or any paid API — these are explicit
     hard constraints, not oversights.
   - Ollama and Piper were unverified/uninstalled as of this session —
     don't assume later sessions installed them without checking
     (`command -v ollama`, `command -v piper` / `pip show piper-tts`).
     Postgres is installed and running natively (`brew services list`).
   - `Conversation.messages` is not a lazy-loaded relationship (removed
     due to an async `MissingGreenlet` footgun) — use
     `ConversationRepository.list_messages()` instead. Prefer the same
     explicit-query pattern for any new cross-entity access in Phase 3+.
   - This file (`PROJECT.md`) must be reconciled against the real repo
     state at the end of every meaningful session, not appended to
     blindly.
