from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.auth import JWTManager
from app.core.config import settings
from app.core.metrics import metrics_collector
from app.db.config import get_db
from app.db.models import User
from app.schemas.common import ApiResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse)
async def health_check() -> ApiResponse:
    return ApiResponse(message="Service is healthy", data={"status": "ok"})


@router.get("/ready", response_model=ApiResponse)
async def readiness_check() -> ApiResponse:
    checks = {
        "api": "ready",
        "database": "not_configured",
        "cache": "not_configured",
    }
    return ApiResponse(message="Service readiness status", data={"checks": checks})


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> PlainTextResponse:
    """Prometheus-compatible metrics export."""
    return PlainTextResponse(metrics_collector.render_prometheus(), media_type="text/plain")


@router.get("/metrics/dashboard", response_model=ApiResponse)
async def metrics_dashboard() -> ApiResponse:
    """JSON snapshot for quick dashboarding and debugging."""
    return ApiResponse(
        message="Metrics dashboard snapshot",
        data=metrics_collector.dashboard_snapshot(),
    )


@router.post("/health/dev/token", response_model=ApiResponse)
async def issue_dev_token(
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Development helper to bootstrap a JWT for local UI testing.

    Disabled in production environments.
    """
    if settings.app_env.lower() == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    demo_email = "demo.user@local.dev"
    user = db.query(User).filter(User.email == demo_email).first()

    if not user:
        user = User(
            email=demo_email,
            name="Demo User",
            timezone="UTC",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = JWTManager.create_access_token(
        user_id=user.id,
        email=user.email,
        scopes=["read", "write"],
    )

    return ApiResponse(
        message="Development token generated",
        data={
            "token": access_token,
            "email": user.email,
            "user_id": user.id,
        },
    )
