# DevManager-Agent

DevManager-Agent is an Agentic DevOps platform for engineering management and code quality governance. It analyzes repository changes, reviews code through specialized agents, tracks delivery health, and produces evidence-based engineering reports with human-governed automation.

The system is read-only by default. It is designed to support engineering managers and technical leads with traceable findings, deterministic scoring, audit records, and controlled approval boundaries.

## Core Capabilities

- Repository ingestion with previous-successful-baseline tracking.
- Diff normalization, file classification, and change-risk analysis.
- Agent-assisted review for correctness, security, reliability, maintainability, and test risk.
- Structured finding validation, deduplication, and deterministic scoring.
- Engineering reports backed by commits, files, CI signals, audit events, and database records.
- Policy-governed automation with no production write actions unless explicitly approved.

## Repository Layout

- `apps/`: API gateway, worker, web UI, and application entry points.
- `services/`: domain services such as PM integration, Git ingestion, change intelligence, finding aggregation, scoring, and audit.
- `packages/`: shared Python, TypeScript, Java, database, Git, LLM, scoring, reporting, and contract modules.
- `migrations/postgres/`: PostgreSQL SQL migration scripts that must be versioned and uploaded with the code.
- `scripts/`: local development, migration, and operational scripts.
- `.github/`: CI workflow configuration.

Product design documents, tests, runtime logs, local caches, virtual environments, and frontend build artifacts are intentionally excluded from version control.

## Technology Stack

- Python 3.12 with `uv` workspace management.
- FastAPI for the API gateway.
- ARQ and Redis for background jobs.
- PostgreSQL 14+ for persistent storage.
- React, TypeScript, and Vite for the web UI.
- Docker Compose for local PostgreSQL and Redis services.

## Database Migrations

SQL migrations are stored in `migrations/postgres/` and are part of the uploadable source set. Apply pending migrations with:

```bash
uv run python scripts/migrate.py
```

The current migration set includes:

- `001_initial_schema.sql`
- `002_add_clone_url.sql`
- `002_add_repository_token.sql`
- `003_add_run_repo_fullname.sql`
- `004_create_settings.sql`
- `005_add_llm_settings.sql`
- `006_add_llm_base_url.sql`
- `007_audit_events_workflow_id_nullable.sql`
- `008_team_ops_foundation.sql`
- `009_team_ops_mirror.sql`
- `010_team_ops_derived.sql`
- `011_team_ops_suggestion.sql`
- `012_pm_sync_cursor.sql`
- `013_team_ops_knowledge.sql`

## Local Development

Install dependencies:

```bash
uv sync
cd apps/web && npm install
```

Start PostgreSQL and Redis with Docker Compose:

```bash
docker compose up -d postgres redis
```

Run database migrations:

```bash
uv run python scripts/migrate.py
```

Start the local development stack:

```bash
./start.sh
```

Stop local services:

```bash
./stop.sh
```

## Configuration

Create a local `.env` file from `.env.example` and adjust values for your environment. Local `.env` files are ignored by Git and must not be committed.

Common settings:

- `DATABASE_URL`
- `REDIS_URL`
- `API_SECRET_KEY`
- LLM provider credentials and base URLs, when enabled.

## Safety Defaults

- No automatic production deployment.
- No automatic pull request merge.
- No unrestricted repository shell execution.
- No employee performance, compensation, promotion, or termination decisions.
- External comments, issue creation, remediation pull requests, and notifications require explicit policy approval.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
