.PHONY: install dev stop migrate test lint format typecheck validate-contracts validate-domain

# ── Dependencies ──────────────────────────────────────────────────────────────
install:
	uv sync --all-extras

# ── Local infra ───────────────────────────────────────────────────────────────
dev:
	docker compose up -d
	@echo "Waiting for PostgreSQL..."
	@until docker compose exec postgres pg_isready -U devmanager -d devmanager >/dev/null 2>&1; do sleep 1; done
	@echo "PostgreSQL ready."

stop:
	docker compose down

# ── Database migration ────────────────────────────────────────────────────────
migrate:
	uv run python scripts/migrate.py

migrate-psql:
	@docker compose exec -T postgres psql -U devmanager -d devmanager \
		< migrations/postgres/001_initial_schema.sql
	@echo "Migration applied."

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	uv run pytest

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy apps/ packages/domain/python/

# ── Contract & domain validation ──────────────────────────────────────────────
validate-contracts:
	@for schema in packages/contracts/schemas/*.json; do python3 -m json.tool $$schema >/dev/null; done
	@python3 -c "import yaml; data=yaml.safe_load(open('packages/contracts/openapi.yaml', encoding='utf-8')); assert data['openapi'].startswith('3.'); assert data['info']['title']"
	@echo "Contracts are valid"

validate-domain:
	@python3 -m py_compile packages/domain/python/devmanager_domain/*.py
	@if command -v javac >/dev/null 2>&1; then javac packages/domain/java/src/main/java/com/devmanager/domain/DomainModels.java; else echo "javac not found; skipped Java compile check"; fi
	@if command -v tsc >/dev/null 2>&1; then tsc --noEmit --target ES2020 packages/domain/typescript/src/index.ts; else echo "tsc not found; skipped TypeScript compile check"; fi
	@find packages/domain/python -type d -name __pycache__ -prune -exec rm -rf {} +
	@find packages/domain/java -name '*.class' -delete 2>/dev/null || true
	@echo "Domain model checks completed"

# ── Code map (regen on pull) ─────────────────────────────────────────────────
pull:
	@bash scripts/pull.sh

code-map-regen:
	@uv run python -m api_gateway.routers.code_map.regen \
	    $(if $(FORCE_FULL),--force-full) \
	    $(if $(SCOPE),--scope=$(SCOPE)) \
	    --prev-head "$${PREV_HEAD:-HEAD~1}" \
	    --new-head "$${NEW_HEAD:-HEAD}" \
	    --maps-dir "$$PWD/docs/code-map" || true
	@echo "code map: regenerated"

# ── CI gate (runs all checks) ─────────────────────────────────────────────────
ci: validate-contracts validate-domain lint test
