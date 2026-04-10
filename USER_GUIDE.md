# User Guide

This guide helps end users and operators run and use the AI Agentic Workflow System.

## 1. Prerequisites

- Docker + Docker Compose (recommended path)
- Or local runtimes:
  - Python 3.11+
  - Node.js 18+
- Access to required API credentials (for enabled integrations)

## 2. Start the System

### Docker Compose

From repository root:

```bash
docker compose up -d --build postgres redis backend frontend
```

Open:

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

### Stop services

```bash
docker compose down
```

## 3. First-Time Access

1. Open the frontend in browser.
2. Authenticate if login is required by your environment configuration.
3. Connect Google account when using Gmail/Calendar features.

## 4. Core Features

### Chat Assistant

- Ask natural-language questions or requests.
- The assistant can route tasks to tools (calendar/email/search) based on intent.

### Tasks and Productivity

- View, track, and manage task-oriented activity through dashboard widgets.

### Calendar

- Fetch schedule views and create/update events when connected.

### Email

- Review and work with email flows when Gmail integration is authorized.

## 5. Troubleshooting

- Frontend unreachable:
  - Check `frontend` container status and port `3000`.
- Backend API errors:
  - Check `backend` container logs and health endpoint.
- OAuth issues:
  - Verify redirect URI and Google client credentials.
- Missing data:
  - Validate Postgres and Redis services are healthy.

Useful commands:

```bash
docker compose ps
docker compose logs backend --tail 200
docker compose logs frontend --tail 200
```

## 6. Local Development Mode (without Docker)

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## 7. Safety and Permissions

- Only connect integrations you intend to use.
- Review approval-required actions before execution.
- Store secrets in environment variables; do not commit sensitive keys.

## 8. Additional References

- Central overview: [README.md](README.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Backend details: [backend/README.md](backend/README.md)
- Frontend details: [frontend/README.md](frontend/README.md)
- Testing: [TESTING.md](TESTING.md)
