# Testing Strategy & Setup

## Overview

Comprehensive testing approach covering unit, integration, and end-to-end tests.

---

## 1. Backend Testing

### Test Structure

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_security.py
│   │   ├── test_audit.py
│   │   └── test_config.py
│   ├── integration/
│   │   ├── test_gmail_flow.py
│   │   ├── test_calendar_flow.py
│   │   ├── test_task_flow.py
│   │   └── test_approval_flow.py
│   └── e2e/
│       ├── test_morning_routine.py
│       └── test_daily_planning.py
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# Specific test file
pytest tests/unit/test_auth.py -v

# By marker
pytest -m "unit" -v
pytest -m "integration" -v
pytest -m "security" -v

# Watch mode
ptw tests/
```

### Test Markers

Add to `conftest.py`:

```python
import pytest

@pytest.mark.unit
def test_unit_example(): pass

@pytest.mark.integration
def test_integration_example(): pass

@pytest.mark.security
def test_security_example(): pass

@pytest.mark.slow
def test_slow_operation(): pass
```

### Example Unit Test

```python
# tests/unit/test_auth.py
import pytest
from app.core.auth import JWTManager

@pytest.mark.unit
class TestJWTManager:
    def test_create_access_token(self):
        token = JWTManager.create_access_token(
            user_id="user123",
            email="user@example.com"
        )
        assert token is not None
        assert isinstance(token, str)
    
    def test_verify_valid_token(self):
        token = JWTManager.create_access_token(
            user_id="user123",
            email="user@example.com"
        )
        payload = JWTManager.verify_token(token)
        assert payload.sub == "user123"
        assert payload.email == "user@example.com"
    
    def test_verify_expired_token(self):
        # Test with expired token logic
        pass
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create tables
    # Base.metadata.create_all(engine)
    yield engine

@pytest.fixture
def client(test_db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)

@pytest.fixture
def valid_token():
    from app.core.auth import JWTManager
    return JWTManager.create_access_token(
        user_id="test_user",
        email="test@example.com"
    )
```

### Coverage Requirements

- **Unit Tests**: > 80% coverage
- **Integration Tests**: > 60% coverage
- **Critical Paths**: 100% (auth, approval, payments)

---

## 2. Frontend Testing

### Test Structure

```
frontend/
├── src/
├── __tests__/
│   ├── unit/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── utils/
│   ├── integration/
│   │   └── flows/
│   └── e2e/
│       └── scenarios/
└── vitest.config.ts
```

### Testing Tools

- **Unit/Integration**: Vitest, React Testing Library
- **E2E**: Playwright or Cypress
- **Type**: TypeScript strict mode
- **Accessibility**: axe-core via @axe-core/react

### Example Unit Test

```typescript
// src/__tests__/unit/components/ChatMessage.test.tsx
import { render, screen } from '@testing-library/react';
import { ChatMessage } from '@/components/ChatMessage';

describe('ChatMessage', () => {
  it('renders user message', () => {
    render(
      <ChatMessage 
        role="user" 
        content="Hello" 
      />
    );
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('applies correct styling for AI response', () => {
    const { container } = render(
      <ChatMessage 
        role="assistant" 
        content="Hi there" 
      />
    );
    expect(container.firstChild).toHaveClass('bg-slate-700');
  });
});
```

### Running Frontend Tests

```bash
# Unit/Integration tests
npm run test

# With UI
npm run test:ui

# Watch mode
npm run test:watch

# E2E tests with Playwright
npm run test:e2e

# Coverage
npm run test:coverage
```

---

## 3. Security Testing

### SAST (Static Application Security Testing)

**Tools:**
- Bandit (Python)
- Semgrep
- CodeQL

```bash
# Bandit (Python)
bandit -r backend/app

# Semgrep
semgrep --config=p/security-audit backend/

# Run as part of CI
```

### DAST (Dynamic Application Security Testing)

**Tools:**
- OWASP ZAP
- Burp Suite Community

```bash
# OWASP ZAP
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://localhost:8000/api/v1
```

### Dependency Scanning

```bash
# pip-audit
pip-audit

# safety
safety check

# Snyk (frontend)
snyk test frontend/
```

### Security Test Examples

```python
# tests/security/test_auth_security.py
@pytest.mark.security
def test_jwt_secret_key_secure():
    """Verify JWT secret is not default."""
    assert settings.jwt_secret_key != "your-very-secure-secret-key"

@pytest.mark.security
def test_password_hashing_secure():
    """Verify passwords are not stored in plaintext."""
    from app.core.security import CryptoUtils
    pwd = "test123"
    hashed = CryptoUtils.hash_password(pwd)
    assert pwd != hashed

@pytest.mark.security
def test_sql_injection_prevention(client):
    """Test SQL injection prevention."""
    response = client.post(
        "/api/v1/tasks",
        json={"title": "'; DROP TABLE tasks; --"}
    )
    assert response.status_code != 500  # Should be handled safely

@pytest.mark.security
async def test_cors_headers(client):
    """Verify CORS headers are set correctly."""
    response = client.get("/api/v1/health")
    assert "Access-Control-Allow-Origin" in response.headers
```

---

## 4. Load & Performance Testing

### Tools

- **Locust** (Python load testing)
- **k6** (JavaScript)
- **Apache JMeter**

### Example Load Test

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_health(self):
        self.client.get("/api/v1/health")
    
    @task(1)
    def create_task(self):
        self.client.post(
            "/api/v1/tasks",
            json={"title": "Load test task"}
        )

# Run with:
# locust -f tests/load/locustfile.py --host=http://localhost:8000
```

---

## 5. Test Coverage Goals

| Component | Target | Status |
|-----------|--------|--------|
| Authentication | 100% | ✅ |
| Authorization | 100% | ✅ |
| Audit Logging | 90% | ✅ |
| Email Integration | 85% | 🔄 |
| Calendar Integration | 85% | 🔄 |
| Task Management | 85% | 🔄 |
| Approval Workflows | 95% | 🔄 |

---

## 6. Continuous Testing

### Pre-commit Hooks

```bash
#!/bin/bash
# .git/hooks/pre-commit

set -e

echo "Running pre-commit tests..."

# Backend
cd backend
pytest tests/ --tb=short
black --check app/
ruff check app/

# Frontend
cd ../frontend
npm run test:ci
npm run lint
npm run type-check

echo "✅ All checks passed"
```

### CI Pipeline Integration

- Tests run automatically on PR
- Coverage reports published
- Failures block merge
- Security tests included

---

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [React Testing Library](https://testing-library.com/react)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
