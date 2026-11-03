from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.core.farm_time import farm_today
from app.services.trend_analytics import build_trend_analysis
from app.services.farm_intelligence import build_farm_intelligence_overview


router = APIRouter(
    prefix="/api/v1/analytics",
    dependencies=[Depends(require_permission("intelligence:view"))],
    tags=["Analytics"],
)


def _subtract_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) - months
    year = total // 12
    month = total % 12 + 1
    return date(year, month, 1)


@router.get("/trends")
def get_trend_analysis(
    months: int = Query(default=12, ge=3, le=36),
    db: Session = Depends(get_db),
):
    end_date = farm_today()
    start_date = _subtract_months(end_date, months - 1)
    return build_trend_analysis(db, start_date, end_date)


@router.get("/overview")
def get_farm_intelligence_overview(
    months: int = Query(default=12, ge=3, le=36),
    db: Session = Depends(get_db),
):
    return build_farm_intelligence_overview(db, months=months)
