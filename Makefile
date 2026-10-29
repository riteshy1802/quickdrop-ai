SHELL := /bin/bash
.DEFAULT_GOAL := help

# Resolve paths relative to this file, including when invoked with make -f.
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND_DIR := $(ROOT_DIR)/backend
FRONTEND_DIR := $(ROOT_DIR)/frontend

UV ?= uv
NPM ?= npm
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
BACKEND_SHUTDOWN_TIMEOUT ?= 5
FRONTEND_PORT ?= 3000

.PHONY: help install install-backend install-frontend infra-up infra-down status \
	migrate migrations migration-current migration-check seed seed-admin backend frontend \
	worker workers worker-docker worker-stop lint typecheck test test-unit build replay

help: ## List available commands
	@awk 'BEGIN {FS = ":.*## "; printf "QuickDrop commands (run from the repository root):\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' "$(ROOT_DIR)/Makefile"

install: install-backend install-frontend ## Install backend and frontend dependencies

install-backend: ## Install locked Python dependencies with uv
	cd "$(BACKEND_DIR)" && $(UV) sync --locked

install-frontend: ## Install frontend dependencies from package-lock.json
	cd "$(FRONTEND_DIR)" && $(NPM) ci

infra-up: ## Start PostgreSQL, Redis and PaySwift (requires root .env)
	cd "$(ROOT_DIR)" && docker compose up -d --wait postgres redis payswift

infra-down: ## Stop Compose services; keep database volumes
	cd "$(ROOT_DIR)" && docker compose down

status: ## Show Compose service status
	cd "$(ROOT_DIR)" && docker compose ps

migrate: ## Apply all pending database migrations
	cd "$(BACKEND_DIR)" && $(UV) run alembic upgrade head

migrations: migrate ## Alias for migrate

migration-current: ## Show the database's current Alembic revision
	cd "$(BACKEND_DIR)" && $(UV) run alembic current

migration-check: ## Check for model/schema differences after migrating
	cd "$(BACKEND_DIR)" && $(UV) run alembic check

seed: ## Import CSV data using the existing idempotent seed script
	cd "$(BACKEND_DIR)" && $(UV) run python -m app.scripts.seed

seed-admin: ## Seed Ops admin from OPS_ADMIN_EMAIL and OPS_ADMIN_PASSWORD
	cd "$(BACKEND_DIR)" && $(UV) run python -m app.scripts.seed_admin

replay: ## Replay historical scenarios locally in a disposable database with mocked payments
	cd "$(BACKEND_DIR)" && $(UV) run python -m app.scripts.replay --local-test-mode

backend: ## Run FastAPI with auto-reload in the foreground
	cd "$(BACKEND_DIR)" && $(UV) run uvicorn app.main:app --reload --timeout-graceful-shutdown "$(BACKEND_SHUTDOWN_TIMEOUT)" --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)"

frontend: ## Run Next.js development server in the foreground
	cd "$(FRONTEND_DIR)" && $(NPM) run dev -- --port "$(FRONTEND_PORT)"

worker: infra-up ## Wait for infrastructure, then run the shared worker in the foreground
	cd "$(BACKEND_DIR)" && $(UV) run python -m app.workers.main

workers: worker ## Alias for worker (one shared worker entry point)

worker-docker: ## Build/start the Compose worker; run migrate first
	cd "$(ROOT_DIR)" && docker compose up -d --build worker

worker-stop: ## Stop the Compose worker
	cd "$(ROOT_DIR)" && docker compose stop worker

lint: ## Check Ruff, Python formatting and ESLint without modifying files
	cd "$(BACKEND_DIR)" && $(UV) run ruff check .
	cd "$(BACKEND_DIR)" && $(UV) run ruff format --check .
	cd "$(FRONTEND_DIR)" && $(NPM) run lint

typecheck: ## Generate Next.js types and check TypeScript
	cd "$(FRONTEND_DIR)" && $(NPM) run typecheck

test: ## Run backend tests (database tests need PostgreSQL and CREATEDB)
	cd "$(BACKEND_DIR)" && $(UV) run pytest -q

test-unit: ## Run backend tests excluding database tests
	cd "$(BACKEND_DIR)" && $(UV) run pytest -q -m 'not database'

build: ## Build the Next.js production application
	cd "$(FRONTEND_DIR)" && $(NPM) run build
