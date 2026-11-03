from typing import Literal
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.auth import get_current_user
from app.models import User
from app.services.void_authorization import preview_void, execute_authorized_void

class PrivateValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                return JSONResponse(status_code=422, content={'detail': [{key: item[key] for key in ('loc', 'msg', 'type')} for item in error.errors()]})
        return safe_handler

router = APIRouter(prefix='/api/v1/void-authorizations', tags=['Owner/Admin Void Authorization'], route_class=PrivateValidationRoute)

class VoidAuthorizationRequest(BaseModel):
    preview_token: str = Field(max_length=4000)
    reason: str = Field(min_length=3, max_length=300)
    owner_username: str | None = Field(default=None, max_length=50)
    owner_password: str | None = Field(default=None, max_length=128, repr=False)
    otp_code: str | None = Field(default=None, max_length=8, repr=False)
    @field_validator('reason', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

@router.get('/preview')
def preview(action: Literal['task', 'resource_usage', 'sale', 'processing'], record_id: int,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return preview_void(db, user, action, record_id)

@router.post('')
def authorize(payload: VoidAuthorizationRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return execute_authorized_void(db, user, payload, request)
    except Exception:
        db.rollback()
        raise
