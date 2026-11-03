"""Authenticated, read-only information about this running farm instance."""

from fastapi import APIRouter, Depends, Response

from app.core.config import settings
from app.core.dependencies import require_permission
from app.services.phone_access import phone_access


router = APIRouter(prefix="/api/v1/system", tags=["System"])


@router.get("/phone-access", dependencies=[Depends(require_permission("dashboard:view"))])
def get_phone_access(response: Response):
    # Network addresses can change while the system is running and must not be
    # retained by shared computers or intermediate caches.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return phone_access(settings.farm_frontend_port)
