# Makefile — quick-start commands for the demo
# Usage: make <target>
# Requires: docker, docker compose, python3, node

.PHONY: help up down logs seed migrate test test-integration \
        stub erp-emit cbp-hold cbp-release dev-api dev-frontend

help:
	@echo ""
	@echo "  Autonomous AI Customs Clearance — Quick Commands"
	@echo ""
	@echo "  Setup & run:"
	@echo "    make up           Start all services (docker compose)"
	@echo "    make down         Stop all services"
	@echo "    make migrate      Run Alembic migrations inside api container"
	@echo "    make seed         Seed 3 synthetic shipments (SHP-001/002/003)"
	@echo ""
	@echo "  Testing:"
	@echo "    make test         Run all backend tests"
	@echo "    make test-integration  Run integration smoke tests only"
	@echo ""
	@echo "  Demo:"
	@echo "    make erp-emit     Emit CARGO_ARRIVED + INVOICE_RECEIVED (once)"
	@echo "    make cbp-hold     Emit CBP_HOLD_RECEIVED for SHP-003"
	@echo "    make cbp-release  Emit CBP_RELEASE_RECEIVED for SHP-003"
	@echo ""
	@echo "  Local dev (no Docker):"
	@echo "    make dev-api      Run FastAPI with reload on port 8000"
	@echo "    make dev-frontend Run Next.js on port 3000"
	@echo "    make stub         Run stub API on port 8001"
	@echo ""

# ── Docker ────────────────────────────────────────────────────────────────────

up:
	@test -f backend/.env || (echo "Creating backend/.env from .env.example..." && cp .env.example backend/.env)
	docker compose up -d
	@echo "→ API:      http://localhost:8000/health"
	@echo "→ Frontend: http://localhost:3000"
	@echo "→ Docs:     http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f api frontend

# ── Database ──────────────────────────────────────────────────────────────────

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed.py

migrate-local:
	cd backend && DATABASE_URL=postgresql://customs:customs@localhost:5432/customs \
	  alembic upgrade head

seed-local:
	cd backend && DATABASE_URL=postgresql://customs:customs@localhost:5432/customs \
	  python scripts/seed.py

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	cd backend && python3 -m pytest tests/ -v

test-integration:
	cd backend && python3 -m pytest tests/integration/ -v

# ── Mock event feeds ──────────────────────────────────────────────────────────

erp-emit:
	cd backend && python3 ../mocks/erp_emitter.py --once

cbp-hold:
	cd backend && python3 ../mocks/cbp_feed.py --scenario hold

cbp-release:
	cd backend && python3 ../mocks/cbp_feed.py --scenario release

# ── Local dev servers ─────────────────────────────────────────────────────────

dev-api:
	cd backend && uvicorn api.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

stub:
	cd stub && uvicorn stub_server:app --reload --port 8001
