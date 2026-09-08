# VoiceOps — Project Instructions

Portfolio-quality real-time voice AI support agent. See `PROJECT.md` for
current build state and `README.md` for architecture/setup.

## Hard constraints

- **$0 recurring cost.** Never add Twilio, ElevenLabs, OpenAI API,
  Anthropic API, Deepgram, AssemblyAI, or any other paid/metered API.
  Everything must run locally: Ollama (LLM), faster-whisper (STT), Piper
  (TTS), PostgreSQL.
- **Business logic never leaves the backend.** The browser only exchanges
  WebSocket messages with FastAPI. It must never talk to the DB or Ollama
  directly.
- **The LLM never executes arbitrary code.** All LLM actions go through the
  typed tool registry (`backend/app/agent/tool_registry.py`): explicit name,
  Pydantic input schema, validation, execution, structured result. No
  `eval`, no dynamic dispatch to arbitrary functions.
- **No fake functionality.** No fake streaming, no stubbed tool calls that
  just return canned data, no simulated STT/TTS in the real pipeline. If a
  feature can't be done properly with local tools, document the limitation
  in the README instead of faking it.
- **Booking/cancelling appointments requires explicit user confirmation**
  before the tool call executes — this is a product requirement, not just a
  UX nicety.
- **No vector database** unless a genuine retrieval need appears that
  Postgres full-text search can't handle. Ask before adding one.
- **No Redis** unless a genuine cross-process/caching need appears (current
  design is single backend process, state in Postgres). Ask before adding
  one.

## Architecture (stable decisions — don't relitigate without reason)

- Backend: FastAPI, `uv`-managed, Python 3.12, async.
- Frontend: Next.js (App Router) + TypeScript + Tailwind, `npm`-managed.
- DB: PostgreSQL, accessed via SQLAlchemy async + repositories (Phase 2).
- Ollama, Piper, faster-whisper voice model files run/live on the host, not
  in Docker — simplifies Apple Silicon acceleration and avoids audio device
  passthrough. Only Postgres is containerized (`docker-compose.yml`).
- Backend package layout is fixed: `api/`, `agent/`, `voice/`, `tools/`,
  `db/`, `services/`, `core/`. Keep responsibilities in the right package —
  don't grow `main.py` or dump logic into one giant module.

## Required commands

Run before considering any phase done:

```bash
make test   # backend: uv run pytest -q
make lint   # backend: ruff check + mypy app; frontend: npm run lint
```

Frontend build check when frontend files change: `cd frontend && npm run build`.

## Development process

This project is built in 13 phases (defined in `PROJECT.md`). For each
phase: implement, run `make test` and `make lint` (fix failures before
proceeding), verify the actual behavior (not just "it compiles"), then
commit with a message describing that phase. Don't start the next phase
with a red test suite. Don't attempt multiple phases' worth of work in one
uncommitted batch — commit at phase boundaries so the history is a usable
build log.

## Notes for future sessions

- `docker`, `ollama`, and `piper` were **not installed** in the dev
  environment as of Phase 1. Whoever runs later phases needs to install
  them per the README before those phases can be verified end-to-end
  (Ollama/Postgres for Phase 2+, Piper for Phase 7).
- Next.js 16 (installed via `create-next-app@latest`) ships an
  `frontend/AGENTS.md` warning that its APIs/conventions may differ from
  training data — read `frontend/node_modules/next/dist/docs/` before
  writing non-trivial App Router code in Phase 10.
