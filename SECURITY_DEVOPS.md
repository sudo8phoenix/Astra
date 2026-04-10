# Security & DevOps Implementation Guide

## Overview

This document outlines the security and DevOps infrastructure implemented for the AI Personal Assistant Agent.

---

## 1. Environment Configuration

### Structure

All environment-specific configurations are managed via `.env` files:

- **Development**: `.env.local` (local testing)
- **Staging**: `.env.staging` (integration testing)
- **Production**: `.env.production` (managed secrets)

### Key Configurations

See [.env.example](.env.example) for all available environment variables.

**Critical Variables:**

```bash
# Authentication
JWT_SECRET_KEY=<use-secure-vault>
GOOGLE_OAUTH_CLIENT_SECRET=<use-secure-vault>

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0

# LLM
GROQ_API_KEY=<use-secure-vault>

# Feature Flags
FEATURE_EMAIL_MANAGEMENT=true
FEATURE_CALENDAR_MANAGEMENT=true
FEATURE_TASK_MANAGEMENT=true
```

### Environment-Specific Behavior

| Setting | Development | Staging | Production |
|---------|-------------|---------|------------|
| `APP_DEBUG` | True | False | False |
| `LOG_LEVEL` | DEBUG | INFO | WARNING |
| `JWT_EXPIRE` | 24h | 24h | 30m |
| `REQUIRE_HTTPS` | False | True | True |
| `CORS_ALLOW_ALL` | True | False | False |

---

## 2. Authentication & Authorization

### JWT (JSON Web Tokens)

**Implementation:** `app/core/auth.py`

#### Token Generation

```python
from app.core.auth import JWTManager

# Create access token
token = JWTManager.create_access_token(
    user_id="user123",
    email="user@example.com",
    scopes=["read", "write"]
)

# Create refresh token
refresh_token = JWTManager.create_refresh_token(
    user_id="user123",
    email="user@example.com"
)
```

#### Token Validation

```python
from app.core.auth import get_current_user
from fastapi import Depends

@app.get("/protected")
async def protected_route(current_user = Depends(get_current_user)):
    return {"user_id": current_user.sub}
```

#### Token Payload

```json
{
  "sub": "user123",
  "email": "user@example.com",
  "scopes": ["read", "write"],
  "exp": 1711270800,
  "iat": 1711184400,
  "jti": "user123_1711184400.123"
}
```

**Token TTL Configuration:**

- Access Token: `JWT_EXPIRATION_HOURS` (default: 24 hours)
- Refresh Token: `JWT_REFRESH_EXPIRATION_DAYS` (default: 7 days)
- Algorithm: `JWT_ALGORITHM` (default: HS256, recommend RS256 for production)

### OAuth 2.0 Flows

**Google Authentication:**

```python
from app.core.auth import OAuth2Manager

# Generate authorization URL
auth_url = OAuth2Manager.get_google_auth_url(state="random_state_token")
# Redirect user to auth_url

# In callback endpoint:
# 1. Validate state parameter
# 2. Exchange authorization code for tokens
# 3. Fetch user info
# 4. Create/update user in database
# 5. Issue JWT tokens
```

**GitHub Authentication:**

```python
auth_url = OAuth2Manager.get_github_auth_url(state="random_state_token")
```

### Scopes & Permissions

**Defined Scopes:**

- `read` - Read-only access
- `write` - Create/modify data
- `admin` - Administrative access
- `email:read` - Read email
- `email:send` - Send email (requires approval)
- `calendar:read` - Read calendar
- `calendar:write` - Create/modify calendar events
- `task:manage` - Manage tasks
- `approval:review` - Review approval workflows

---

## 3. Secrets Management

### Strategy

Three-tier approach based on environment:

#### Development
- Environment variables from `.env.local`
- No external vault required
- Suitable for local development

#### Staging
- Environment variables
- Optional: Encrypted local storage

#### Production
- **HashiCorp Vault** or **AWS Secrets Manager**
- Never commit secrets to version control
- Automatic secret rotation

### Implementation

**`app/core/security.py`**

```python
from app.core.security import SecretsManager

# Get secret
api_key = SecretsManager.get_secret("GROQ_API_KEY")

# Store secret (dev) or vault (prod)
SecretsManager.store_secret("NEW_API_KEY", "value")
```

### Production Integration

**AWS Secrets Manager Example:**

```python
import boto3

def get_secret_from_aws(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

# In SecretsManager._get_from_vault():
if settings.app_env == "production":
    return get_secret_from_aws(key)
```

**HashiCorp Vault Example:**

```python
import hvac

def get_secret_from_vault(secret_path):
    client = hvac.Client(url='https://vault.example.com', token=os.getenv('VAULT_TOKEN'))
    response = client.secrets.kv.read_secret_version(path=secret_path)
    return response['data']['data']['value']
```

### Encryption

**Password Hashing:**

```python
from app.core.security import CryptoUtils

# Hash password
hashed = CryptoUtils.hash_password("user_password")
storage.save_user(user_id, hashed)

# Verify password
is_valid = CryptoUtils.verify_password("login_password", hashed)
```

**Token Encryption:**

```python
# Encrypt sensitive token for storage
encrypted = CredentialStore.encrypt_token(oauth_token)
db.save_encrypted_token(user_id, encrypted)

# Decrypt when needed
decrypted = CredentialStore.decrypt_token(encrypted)
```

**⚠️ Note:** For production, replace basic encryption with Fernet or AES-256.

---

## 4. Audit Logging

### Schema

**Audit Log Entry:**

```python
from app.core.audit import AuditLogEntry, AuditActionType, AuditResourceType

entry = AuditLogEntry(
    user_id="user123",
    action=AuditActionType.EMAIL_SEND,
    resource_type=AuditResourceType.EMAIL,
    resource_id="email_456",
    success=True,
    severity="info",
    approval_status="approved",
    details=[
        AuditLogDetail(key="recipient", new_value="john@example.com")
    ]
)
```

### Database Schema

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(255) UNIQUE NOT NULL,
    trace_id VARCHAR(255),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    user_id VARCHAR(255),
    user_email VARCHAR(255),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255),
    http_method VARCHAR(10),
    http_path VARCHAR(500),
    http_status_code INTEGER,
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    success BOOLEAN DEFAULT TRUE,
    severity VARCHAR(20) DEFAULT 'info',
    details JSONB,
    error_message TEXT,
    requires_approval BOOLEAN DEFAULT FALSE,
    approval_status VARCHAR(20),
    approved_by VARCHAR(255),
    approval_reason TEXT
);

-- Indexes
CREATE INDEX idx_audit_user_timestamp ON audit_logs(user_id, timestamp);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_action ON audit_logs(action, timestamp);
```

### Usage

```python
from app.core.audit import AuditLogger, AuditActionType, AuditResourceType

logger = AuditLogger(db_session)

# Log email send action
await logger.log_email_action(
    user_id="user123",
    action=AuditActionType.EMAIL_SEND,
    resource_id="email123",
    success=True,
    requires_approval=True,
    approval_status="approved",
)

# Log approval action
await logger.log_approval_action(
    user_id="user123",
    action=AuditActionType.EMAIL_APPROVED,
    resource_type=AuditResourceType.EMAIL,
    resource_id="email123",
    success=True,
    approved_by="approver@example.com",
    approval_reason="Verified content"
)
```

### Approval Workflow Logging

```sql
CREATE TABLE approval_logs (
    id SERIAL PRIMARY KEY,
    approval_id VARCHAR(255) UNIQUE NOT NULL,
    audit_id VARCHAR(255),
    requested_by VARCHAR(255) NOT NULL,
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected, expired
    decided_by VARCHAR(255),
    decided_at TIMESTAMP WITH TIME ZONE,
    decision_reason TEXT,
    requested_details JSONB,
    approval_context JSONB
);
```

---

## 5. CI/CD Pipeline

### GitHub Actions Workflows

#### Backend CI (`backend-ci.yml`)

**Jobs:**

1. **Lint** - Code quality checks
   - Black formatting
   - isort import sorting
   - Ruff linting
   - mypy type checking

2. **Security** - Vulnerability scanning
   - pip-audit dependency check
   - safety vulnerability scan
   - Bandit SAST

3. **Tests** - Unit & integration tests
   - PostgreSQL test database
   - Redis test cache
   - pytest with coverage
   - Codecov upload

4. **Build** - Docker image creation
   - Multi-stage Docker build
   - Push to GHCR

5. **Dependency Check** - SCA scanning

#### Frontend CI (`frontend-ci.yml`)

**Jobs:**

1. **Lint** - Code quality
   - ESLint
   - Prettier formatting

2. **Type Check** - TypeScript validation

3. **Tests** - Unit tests with coverage

4. **Build** - Production build

5. **A11y** - Accessibility testing

6. **Security** - Snyk security scan

#### Docker Build (`docker-build.yml`)

- Builds and pushes Docker images to GHCR
- Triggered on main/staging push
- Tags with branch, version, and SHA

### Running Tests Locally

```bash
# Backend tests
cd backend
pytest tests/ -v --cov=app

# Frontend tests
cd frontend
npm run test:coverage

# Code formatting
cd backend
black app/
isort app/

cd frontend
npm run format
```

### Pre-commit Hooks

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

# Backend checks
cd backend
black app/ && isort app/ && ruff check app/

# Frontend checks
cd ../frontend
npm run lint:fix && npm run format

cd ..
```

---

## 6. Docker & Container Security

### Backend Dockerfile

- Multi-stage build (builder + runtime)
- Non-root user (`appuser`)
- Minimal base image (`python:3.11-slim`)
- Health checks enabled

### Frontend Dockerfile

- Multi-stage build (builder + nginx)
- Non-root user
- Nginx Alpine base
- Security headers in nginx config

### Docker Compose (`docker-compose.yml`)

**Services:**

- PostgreSQL 16
- Redis 7
- Backend API
- Frontend (Nginx)
- Prometheus (metrics)
- Grafana (dashboards)
- Elasticsearch (logs)
- Kibana (log visualization)

**Usage:**

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Clean up volumes
docker-compose down -v
```

---

## 7. API Security Headers

### Recommended Headers

```python
from fastapi.middleware import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
```

---

## 8. Rate Limiting & Throttling

**Planned Implementation:**

- Global rate limit: 100 req/min per IP
- Per-user limit: 1000 req/day
- LLM token limits: `LLM_DAILY_TOKEN_LIMIT`
- Cost threshold: `LLM_COST_THRESHOLD_CENTS`

---

## 9. Monitoring & Observability

### Prometheus Metrics

- Request latency
- Error rates
- LLM token usage
- Database query duration
- Cache hit/miss rates

### Grafana Dashboards

- Request latency distribution
- Error rate trends
- LLM cost analysis
- Approval workflow metrics

### ELK Stack (Logging)

- Centralized log aggregation
- Structured JSON logging
- Searchable by user, action, resource

---

## 10. Deployment Checklist

- [ ] Secrets configured in vault (prod)
- [ ] Database migrations applied
- [ ] SSL/TLS certificates configured
- [ ] CORS origins configured
- [ ] Audit logging enabled
- [ ] Monitoring alerts configured
- [ ] Rate limiting enabled
- [ ] Security headers validated
- [ ] OAuth credentials registered
- [ ] Backup strategy tested

---

## References

- [OWASP Security Checklist](https://owasp.org/www-project-web-security-testing-guide/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [Docker Security](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
