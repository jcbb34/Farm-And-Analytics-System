"""Small, read-only payloads for resource pages and Dashboard panels."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.services.resource_lists import crop_summary, crop_dashboard, crop_listing, crop_yields, livestock_dashboard, livestock_listing, livestock_records, crop_chart, livestock_chart

router = APIRouter(prefix="/api/v1/display", tags=["Display data"])


@router.get("/crops", dependencies=[Depends(require_permission("crops:view"))])
def crops_page(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=120), crop_type: str = "All", status_filter: str = "Active Crops",
    field: str = "All", planting_date: date | None = None, include_overview: bool = True, db: Session = Depends(get_db)):
    if status_filter not in {"All", "Active Crops", "Archived", "Ready for Harvest", "Harvesting", "Growing", "Fully Harvested/Completed"}:
        raise HTTPException(422, "Invalid crop status filter.")
    return crop_listing(db, offset=offset, limit=limit, search=search, crop_type=crop_type,
        status_filter=status_filter, field=field, planting_date=planting_date, include_overview=include_overview)


@router.get("/crops/summary", dependencies=[Depends(require_permission("crops:view"))])
def crops_summary(db: Session = Depends(get_db)):
    return crop_summary(db)


@router.get("/crops/overview", dependencies=[Depends(require_permission("crops:view"))])
def crops_overview(start_date: date, end_date: date, db: Session = Depends(get_db)):
    if start_date > end_date: raise HTTPException(422, "The start date must not follow the end date.")
    return crop_dashboard(db, start_date, end_date)


@router.get("/crop-yields", dependencies=[Depends(require_permission("crops:view"))])
def crop_yields_page(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    return crop_yields(db, offset, limit)


@router.get("/crops/chart", dependencies=[Depends(require_permission("crops:view"))])
def crop_chart_page(start_date: date, end_date: date, db: Session = Depends(get_db)):
    if start_date > end_date: raise HTTPException(422, "The start date must not follow the end date.")
    return {"items": crop_chart(db, start_date, end_date)}


@router.get("/livestock", dependencies=[Depends(require_permission("livestock:view"))])
def livestock_page(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=120), animal_type: str = "All", health_status: str = "All", pen: str = "All",
    db: Session = Depends(get_db)):
    return livestock_listing(db, offset=offset, limit=limit, search=search, animal_type=animal_type, health_status=health_status, pen=pen)


@router.get("/livestock/overview", dependencies=[Depends(require_permission("livestock:view"))])
def livestock_summary(start_date: date, end_date: date, db: Session = Depends(get_db)):
    if start_date > end_date: raise HTTPException(422, "The start date must not follow the end date.")
    return livestock_dashboard(db, start_date, end_date)


@router.get("/livestock/records", dependencies=[Depends(require_permission("livestock:view"))])
def livestock_history(kind: str = Query("vaccinations", pattern="^(vaccinations|feeding)$"),
    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    return livestock_records(db, kind, offset, limit)


@router.get("/livestock/chart", dependencies=[Depends(require_permission("livestock:view"))])
def livestock_chart_page(start_date: date, end_date: date, db: Session = Depends(get_db)):
    if start_date > end_date: raise HTTPException(422, "The start date must not follow the end date.")
    return {"items": livestock_chart(db, start_date, end_date)}
