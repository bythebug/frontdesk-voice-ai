.PHONY: install dev-backend dev-frontend test lint db-up db-down

install:
	cd backend && uv sync
	cd frontend && npm install

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run mypy app
	cd frontend && npm run lint

db-up:
	brew services start postgresql@16

db-down:
	brew services stop postgresql@16
