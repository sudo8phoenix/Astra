# AI Personal Assistant Backend

Production-oriented FastAPI backend for conversational planning, task management, calendar operations, and Gmail workflows.

## Overview

This service provides:

- REST APIs for chat, tasks, calendar, and email workflows
- Agent orchestration (planner, router, tool execution, response synthesis)
- Google OAuth integrations (Gmail and Calendar)
- PostgreSQL persistence with SQLAlchemy and Alembic
- Redis-backed caching and runtime state support

## Technology Stack

- Python 3.11
- FastAPI + Uvicorn
- SQLAlchemy + Alembic
- PostgreSQL + Redis
- LangChain / LangGraph + Groq
- Google APIs (Gmail, Calendar)

## Repository Layout

```text
backend/
	app/
		agent/            # Planner/router/tools orchestration
		api/              # Versioned API endpoints
		core/             # Config, auth, security, utilities
		db/               # ORM models and DB integration
		integrations/     # External connectors (Google, etc.)
		repositories/     # Data access layer
		schemas/          # Request/response contracts
		services/         # Domain and integration services
	alembic/            # Database migrations
	tests/              # Unit and integration tests
```

## Local Development

### 1. Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Set values for database, Redis, JWT, Groq, and Google OAuth credentials.

### 3. Run the API

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation:

- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Docker Workflow

From the workspace root:

```bash
docker-compose up --build -d backend
```

Or from the backend folder:

```bash
docker build -t ai-assistant-api:latest .
docker run -p 8000:8000 --env-file .env ai-assistant-api:latest
```

## Database and Migrations

```bash
cd backend
alembic upgrade head
```

Create a new migration:

```bash
alembic revision --autogenerate -m "describe_change"
```

## Testing

```bash
cd backend
pytest
```

Run specific test suites:

```bash
pytest tests/unit
pytest tests/integration
```

## Security and Operations

- JWT-based authentication with scoped access
- OAuth token handling for external providers
- Structured logging and audit-friendly events
- Dependency and security scanning in CI

For security implementation details, see [../SECURITY_DEVOPS.md](../SECURITY_DEVOPS.md).

## Troubleshooting

- Import/module errors: ensure virtual environment is active and dependencies are installed.
- Database connection failures: verify `DATABASE_URL` and Postgres availability.
- OAuth callback issues: confirm provider redirect URIs match your configured callback endpoint.
- Unauthorized responses: validate JWT secret, token lifetime, and scopes.

## Additional References

- [../TESTING.md](../TESTING.md)
- [../DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md)
- [.env.example](.env.example)
