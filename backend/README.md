# Backend - AI Personal Assistant API

FastAPI-based backend for the AI Personal Assistant agent system.

## 🚀 Quick Start

```bash
# Setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your configuration

# Run
uvicorn app.main:app --reload

# Access API docs
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

## 🔒 Security Features (Agent D)

### Authentication & Authorization

- **JWT Tokens** with revocation support (JTI blacklist)
- **OAuth 2.0** (Google, GitHub)
- **Token Refresh** mechanism
- **Secure Scopes** for fine-grained permissions

### Secrets Management

- Environment variables (dev/staging)
- Vault integration ready (AWS/HashiCorp)
- Encrypted credential storage
- Automatic token encryption

### Audit Logging

- Comprehensive action tracking (25+ types)
- Approval workflow logging
- Immutable audit trail in database
- User activity history

### CI/CD Security

- SAST (Bandit)
- Dependency scanning (pip-audit, safety)
- Docker image scanning

## 📁 Project Structure

```
app/
├── core/              # Core functionality
│   ├── config.py      # Settings & environment
│   ├── auth.py        # JWT & OAuth (NEW)
│   ├── security.py    # Secrets & crypto (NEW)
│   └── audit.py       # Audit logging (NEW)
├── api/               # API routes
│   └── v1/
│       ├── router.py
│       └── endpoints/
├── db/                # Database
│   ├── config.py
│   └── migrations/    # Alembic (NEW)
└── schemas/           # Data models
```

## ⚙️ Configuration

**Environment Variables** (see `.env.example`):

- Application (debug, origins, etc.)
- Database (PostgreSQL)
- Cache (Redis)
- Authentication (JWT, OAuth)
- External APIs (Groq, Gmail, Calendar)
- Logging & Monitoring
- Feature Flags

## 🧑‍💻 Development Notes

```bash
# Run backend from the backend folder
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs are available at `http://localhost:8000/docs`
- ReDoc is available at `http://localhost:8000/redoc`
- Update environment variables in `.env` before starting local services

## 🔗 Dependencies Installed

- **Framework**: FastAPI, Uvicorn
- **Database**: SQLAlchemy, Alembic, psycopg2
- **Cache**: Redis
- **Auth**: PyJWT, cryptography, passlib
- **LLM**: LangChain, LangGraph, Groq
- **External APIs**: Google API client
- **Security**: bandit, pip-audit, safety
- **Code Quality**: black, isort, ruff, mypy

## 🐳 Docker

```bash
# Build
docker build -t ai-assistant-api:latest .

# Run
docker run -p 8000:8000 -e DATABASE_URL=postgresql://... ai-assistant-api:latest

# Or use docker-compose
docker-compose up backend
```

## 🚀 Deployment Notes

- Set production-grade values for `DATABASE_URL`, `REDIS_URL`, JWT settings, and OAuth credentials.
- Ensure CORS and allowed origins are restricted to trusted frontend domains.
- Use a reverse proxy (Nginx or equivalent) with TLS termination in production.
- Run Alembic migrations before serving traffic.

## 🆘 Troubleshooting

- `ModuleNotFoundError`: Activate the virtual environment and reinstall requirements.
- DB connection errors: Verify `DATABASE_URL` and that PostgreSQL is reachable.
- OAuth callback failures: Confirm callback URLs match provider console settings.
- 401/403 responses: Check JWT secret, token expiration, and required scopes.

## 📚 Documentation

- **[SECURITY_DEVOPS.md](../SECURITY_DEVOPS.md)** - Complete security guide
- **[AGENT_D_COMPLETION.md](../AGENT_D_COMPLETION.md)** - Delivery summary
- **[.env.example](.env.example)** - Configuration template
