from datetime import date
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.auth import get_current_user
from app.services.archive_service import list_archives, archive_impact, change_archive_state, permanent_delete

router = APIRouter(prefix='/api/v1/archives', tags=['Archived Records'])

class ArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def required_reason(cls, value):
        if not value.strip(): raise ValueError('An archive reason is required.')
        return value.strip()

@router.get('')
def archives(module: str | None = None, search: str = Query('', max_length=150), date_from: date | None = None,
             date_to: date | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
             focus_id: int | None = Query(None, gt=0), counts_only: bool = False, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    return list_archives(db, actor, module=module, search=search, date_from=date_from, date_to=date_to, offset=offset, limit=limit, focus_id=focus_id, counts_only=counts_only)

@router.get('/{module}/{record_id}/impact')
def impact(module: str, record_id: int, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    return archive_impact(db, module, record_id, actor)

@router.post('/{module}/{record_id}/archive')
def archive(module: str, record_id: int, payload: ArchiveRequest, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    record = change_archive_state(db, module, record_id, actor, archive=True, reason=payload.reason)
    db.commit()
    return {'id': record.id, 'archived': True}

@router.post('/{module}/{record_id}/restore')
def restore(module: str, record_id: int, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    record = change_archive_state(db, module, record_id, actor, archive=False)
    db.commit()
    return {'id': record.id, 'archived': False}

@router.delete('/{module}/{record_id}')
def delete(module: str, record_id: int, db: Session = Depends(get_db), actor=Depends(get_current_user)):
    permanent_delete(db, module, record_id, actor)
    db.commit()
    return Response(status_code=204)
