"""API v1 router."""

import logging

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.plans import router as plans_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(plans_router)

logger = logging.getLogger(__name__)


@api_router.get("/health")
def health() -> dict[str, str]:
	logger.info("health_check_completed")
	return {"status": "ok"}
