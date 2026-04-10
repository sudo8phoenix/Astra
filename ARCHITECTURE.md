# Architecture

This document describes the system architecture for the AI Agentic Workflow System.

## 1. High-Level Topology

```text
[Web Client]
   |
   v
[Frontend (React/Vite/Nginx)]
   |
   v
[Backend API (FastAPI + Agent Orchestration)]
   |            |                 |
   |            |                 +--> [External APIs: Gmail, Google Calendar, Serp]
   |            |
   |            +--> [Redis: cache/runtime state]
   |
   +--> [PostgreSQL: persistent data]

[Monitoring: Prometheus + Grafana (+ optional ELK)]
```

## 2. Backend Architecture

Primary backend areas:

- `app/api`: API routing, endpoint contracts, and request handling
- `app/agent`: orchestration, planning, routing, and tool invocation
- `app/services`: domain and integration service logic
- `app/repositories`: data access and persistence boundaries
- `app/integrations`: external platform connectors
- `app/core`: config, security, and foundational runtime behavior
- `app/cache`: cache configuration and state plumbing

Key qualities:

- Separation of concerns between transport, orchestration, domain logic, and storage
- Tool-driven agent workflows for calendar, email, and search capabilities
- OAuth-aware integration paths for Google-connected features

## 3. Frontend Architecture

Primary frontend areas:

- `src/components`: reusable UI modules and dashboard widgets
- `src/pages`: route/page-level compositions
- `src/lib`: API client and utility layer
- `src/App.jsx`: root application orchestration

Key qualities:

- Componentized dashboard patterns
- Chat-centric interaction model
- Responsive design for desktop/mobile operation

## 4. Data and State Flow

1. User interacts with the frontend dashboard/chat.
2. Frontend calls backend REST/WebSocket endpoints.
3. Backend orchestrates decisioning and tool execution.
4. Services/repositories fetch or persist data in PostgreSQL.
5. Cache/runtime state is stored/retrieved via Redis where appropriate.
6. External integrations are invoked (Gmail/Calendar/etc.) based on user intent and permissions.
7. Response is synthesized and returned to frontend.

## 5. Deployment Architecture

Primary containerized services from [docker-compose.yml](docker-compose.yml):

- `postgres`
- `redis`
- `backend`
- `frontend`
- `prometheus`
- `grafana`
- `elasticsearch` (optional observability stack)
- `kibana` (optional observability stack)

Network model:

- Shared `ai-network` bridge for service-to-service communication
- Public exposure on configured host ports (3000, 8000, 5432, 6379, etc.)

## 6. Security Boundaries

- OAuth 2.0 flows for Google integrations
- JWT authentication for application requests
- Config-driven secrets and service credentials
- Human approval flows for sensitive actions where implemented

## 7. Observability and Operations

- Health endpoints for service readiness/liveness
- Metrics via Prometheus + Grafana
- Optional log analytics via ELK components
- Test matrix and validation artifacts tracked in root docs

## 8. Architectural Impact Summary

Recent system changes increase overall capability in these dimensions:

- Feature breadth: expanded endpoint and UI coverage for user workflows
- Operational confidence: stronger readiness/testing evidence in repository docs
- Maintainability: clearer modular boundaries between orchestration, services, and UI layers
- Scalability path: containerized, monitored baseline ready for staged rollout
