from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.auth_google import router as auth_google_router
from app.api.v1.endpoints.tasks import router as tasks_router
from app.api.v1.endpoints.calendar import router as calendar_router
from app.api.v1.endpoints.planning import router as planning_router
from app.api.v1.endpoints.emails import router as emails_router
from app.api.v1.endpoints.approvals import router as approvals_router
from app.api.v1.endpoints.websocket import router as websocket_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.notes import router as notes_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_google_router)
router.include_router(tasks_router)
router.include_router(calendar_router)
router.include_router(planning_router)
router.include_router(emails_router)
router.include_router(approvals_router)
router.include_router(websocket_router)
router.include_router(chat_router)
router.include_router(users_router)
router.include_router(notes_router)

