from typing import Literal
from fastapi import APIRouter, Depends
from app.routers.auth import get_current_user
from app.services.location_reference import catalogue, choices

router = APIRouter(prefix='/api/v1/reference/locations', tags=['Address Reference'], dependencies=[Depends(get_current_user)])

@router.get('')
def list_locations(level: Literal['provinces', 'cities', 'barangays'], parent_code: str | None = None):
    return {'items': choices(level, parent_code), 'version': catalogue()['version']}
