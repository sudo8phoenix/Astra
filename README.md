# AI Agentic Workflow System

Central documentation hub for the AI Personal Assistant platform.

This repository contains a production-oriented, full-stack assistant system with conversational orchestration, task and calendar automation, email workflows, and operational monitoring.

## What This System Does

- Runs a multi-agent assistant flow for planning and tool execution
- Exposes backend APIs and WebSocket channels for assistant interactions
- Provides a frontend dashboard for chat, tasks, calendar, email, and productivity workflows
- Integrates with Google OAuth, Gmail, and Google Calendar
- Uses PostgreSQL for persistence and Redis for cache/state
- Supports containerized deployment with monitoring components

## System Impact

The latest implementation across backend and frontend improves:

- Reliability: hardened API flows and integration handling in key endpoints
- Usability: richer dashboard/chat UX with more complete widget and layout coverage
- Operational readiness: improved deployment and test validation artifacts already included in this repo
- Extensibility: modular service/repository/tool structure that supports adding new capabilities safely

## Architecture At A Glance

- Frontend: React + Vite + Tailwind, served by Nginx in containers
- Backend: FastAPI service with agent orchestration and integration modules
- Data layer: PostgreSQL (primary), Redis (cache/runtime state)
- Integrations: Gmail API, Google Calendar API, OAuth 2.0
- Ops/Monitoring: Docker Compose, Prometheus, Grafana, optional ELK stack

For full architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Repository Layout

```text
backend/      FastAPI app, agent orchestration, services, tests, migrations
frontend/     React dashboard app and UI components
monitoring/   Prometheus and Grafana setup
SETUP_SCRIPTS/ Bootstrapping and utility scripts
```

## Quick Start

### Option A: Docker Compose (recommended)

1. Create and populate environment files/secrets required by backend integrations.
2. From repo root, start core services:

```bash
docker compose up -d --build postgres redis backend frontend
```

3. Open apps:
- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

### Option B: Local split run

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

## Core Docs

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- User Guide: [USER_GUIDE.md](USER_GUIDE.md)
- Backend details: [backend/README.md](backend/README.md)
- Frontend details: [frontend/README.md](frontend/README.md)
- Security and ops: [SECURITY_DEVOPS.md](SECURITY_DEVOPS.md)
- Testing: [TESTING.md](TESTING.md)
- Deployment readiness: [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md)

## Notes

- This root README is the central entry point for the repository.
- Service-specific READMEs remain available for implementation-level details.
