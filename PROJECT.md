# Project State

## Last Verified

2026-09-08 (this session — initial project creation, Phase 1 complete)

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

**PARTIALLY COMPLETE** — Phase 1 of 13 done and verified. Phases 2–13 NOT
STARTED.

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

**Not yet committed to git** — see Next Task.

## In Progress

Nothing mid-flight. Phase 1 files are written and verified but not yet
committed.

## Next Task

1. `git add` the Phase 1 files and commit (message describing Phase 1;
   Co-Authored-By trailer per this session's attribution instructions).
2. Begin **Phase 2 — Database + models + migrations**:
   - Design SQLAlchemy async models for `customers`, `appointments`,
     `providers`, `appointment_types`, `availability`, `conversations`,
     `messages`, `tool_calls`, `call_summaries`.
   - Add `sqlalchemy[asyncio]`, `asyncpg`, and a migration tool (Alembic —
     confirm it's genuinely warranted before adding; it's the standard
     choice for SQLAlchemy migrations so likely yes) to `backend/pyproject.toml`.
   - Requires Postgres running: `docker compose up -d postgres` (Docker is
     **not installed** in this dev environment as of Phase 1 — needs
     installing, e.g. Docker Desktop or `brew install --cask docker`,
     before Phase 2 can be verified against a real DB).
   - Seed data for the fictional dental clinic (providers, appointment
     types, opening-hours-driven availability, knowledge base articles).
   - Unit tests for models/repositories against a real (or test) Postgres
     instance.

## Remaining Work

### Required (per the 13-phase plan)

- Phase 2: Database + models + migrations.
- Phase 3: Appointment/customer/knowledge tools (typed tool registry).
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
- `backend/app/{api,agent,voice,tools,db,services}/`: empty packages
  (`__init__.py` only), structure only, no logic yet.
- `frontend/`: default Next.js template, unmodified.
- `docker-compose.yml`: Postgres service only.
- No database schema, no Ollama integration, no STT/TTS, no WebSocket
  handler, no tool registry, no frontend dashboard yet.

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
- **`uv` for backend, `npm` for frontend.** Reason: both already installed,
  each is that ecosystem's standard lockfile-based tool per the global
  CLAUDE.md preference for existing tooling. Status: stable.

## Dependencies

Backend (`backend/pyproject.toml`):
- `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `websockets` — core
  web/async framework and config.
- Dev: `pytest`, `pytest-asyncio`, `httpx` (FastAPI TestClient), `ruff`
  (lint/format), `mypy` (type check).
- Not yet added (planned): `sqlalchemy[asyncio]`, `asyncpg`, `alembic`
  (Phase 2); `faster-whisper` (Phase 6); an Ollama HTTP client — likely
  just `httpx` again, no new dependency (Phase 4); Piper is invoked as a
  local process/binary or via the `piper-tts` pip package (Phase 7,
  decision TBD).

Frontend (`frontend/package.json`): default `create-next-app` deps
(`next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `eslint`,
`eslint-config-next`). Nothing added yet beyond the template.

## Commands

Verified this session:

```bash
cd backend && uv sync                          # installs backend deps
cd backend && uv run pytest -q                 # 1 passed
cd backend && uv run ruff check .              # clean
cd backend && uv run mypy app                  # clean
cd backend && uv run uvicorn app.main:app --reload --port 8000  # not yet run, but wired correctly (health test uses TestClient against the same app)
cd frontend && npm install                     # succeeded during create-next-app
cd frontend && npm run build                   # compiled successfully
```

From repo root (Makefile, not yet exercised directly but mirrors the above):
`make install`, `make dev-backend`, `make dev-frontend`, `make test`,
`make lint`, `make db-up`, `make db-down`.

Not verified: `docker compose up -d postgres` (Docker not installed in this
environment — REQUIRES VERIFICATION once Docker is available).

## Verification

- 2026-09-08: `uv run pytest -q` in `backend/` → `1 passed`.
- 2026-09-08: `uv run ruff check .` in `backend/` → no errors (after fixing
  one line-length violation in `logging.py`).
- 2026-09-08: `uv run mypy app` in `backend/` → "Success: no issues found
  in 11 source files."
- 2026-09-08: `npm run build` in `frontend/` → "Compiled successfully",
  static pages generated for `/` and `/_not-found`.
- Not verified: actual browser load of the frontend dev server; actual
  `uvicorn` server start (only the FastAPI app object was tested, via
  `TestClient`).

## Known Issues

- Docker, Ollama, and Piper are **not installed** in this dev environment.
  Nothing beyond Phase 1 can be end-to-end verified until they are.
- System `python3` is 3.9.6 (too old for this project) — irrelevant in
  practice since `uv` manages its own 3.12+ interpreter for the backend,
  but worth knowing if anyone runs backend code outside `uv run`.
- No `piper` Homebrew formula exists; Piper must be installed via
  `pip install piper-tts` or a downloaded release binary (documented in
  README).

## Blockers

None currently. Phase 2 needs Postgres reachable (via Docker or a native
install) to verify against a real database — flagged above, not yet a
hard blocker since Phase 2 work can start with schema/model code before
requiring a live DB connection.

## Files and Components

| Path | Purpose | State |
|---|---|---|
| `backend/app/main.py` | FastAPI app entrypoint | Implemented (`/health` only) |
| `backend/app/core/config.py` | Settings/env config | Implemented |
| `backend/app/core/logging.py` | Structured JSON logging | Implemented |
| `backend/app/{api,agent,voice,tools,db,services}/` | Fixed package layout for future phases | Structure only |
| `backend/tests/test_health.py` | Health endpoint test | Implemented, passing |
| `frontend/` | Next.js dashboard | Default template only |
| `docker-compose.yml` | Local Postgres | Implemented, unverified (no Docker) |
| `Makefile` | Dev command shortcuts | Implemented, mirrors verified commands |
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
  committing Phase 1, then starting Phase 2 (needs Docker installed to
  fully verify against a live Postgres instance).

## Handoff Notes

1. **What are we building?** VoiceOps — a local-only, real-time voice AI
   support agent (FastAPI/WebSocket/faster-whisper/Ollama/Piper/Postgres
   backend, Next.js frontend) for a fictional dental clinic, built as a
   13-phase portfolio project. Full spec is in the original user request;
   the durable constraints/decisions distilled from it live in `CLAUDE.md`
   and this file's Requirements/Important Decisions sections.
2. **Where are we now?** Phase 1 (repo structure + tooling) is done and
   verified but **not yet committed to git** as of the end of this session
   (check `git log`/`git status` to confirm current state — don't trust
   this line blindly if time has passed).
3. **What was most recently completed?** Backend FastAPI skeleton with
   config/logging/health endpoint + passing tests/lint/mypy; frontend
   Next.js scaffold that builds cleanly; docker-compose.yml (Postgres
   only); README/CLAUDE.md/PROJECT.md.
4. **What remains?** Phases 2–13, in order — see Remaining Work. Phase 2
   (DB/models/migrations) is next.
5. **What should happen next?** Commit Phase 1, then implement Phase 2.
   Docker needs to be installed (`brew install --cask docker` or similar)
   before Phase 2's database work can be verified end-to-end against a
   live Postgres — flag this to the user if it's still missing.
6. **What must the next Claude be careful about?**
   - Don't re-scaffold what already exists — check `git log` and this file
     first.
   - Don't mark a phase complete without actually running its
     tests/lint/verification (see `CLAUDE.md` Required Commands).
   - Don't add Redis, a vector DB, or any paid API — these are explicit
     hard constraints, not oversights.
   - Ollama/Piper/Docker were unverified/uninstalled as of Phase 1 — don't
     assume later sessions installed them without checking
     (`command -v ollama`, `command -v docker`, etc.).
   - This file (`PROJECT.md`) must be reconciled against the real repo
     state at the end of every meaningful session, not appended to
     blindly.
