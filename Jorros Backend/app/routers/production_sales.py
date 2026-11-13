from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_permission
from app.models import (
    Crop,
    Livestock,
    LivestockProcessingRecord,
    LivestockProductionRecord,
    LivestockReproductionRecord,
    LivestockSale,
    LivestockSaleItem,
    LivestockSalePayment,
    User,
)
from app.routers.auth import get_current_user
from app.schemas.production_sales import (
    OverviewResponse,
    ProcessingCreate,
    ProcessingResponse,
    ProcessingVoidRequest,
    ProductionCreate,
    ProductionResponse,
    ReproductionCreate,
    ReproductionResponse,
    SaleCreate,
    SalePaymentCreate,
    SalePaymentResponse,
    SalePaymentResult,
    SaleResponse,
    SaleVoidRequest,
)
from app.services.production_overview import source_sales_totals, production_stock_totals
from app.services.sale_stock import production_availability, stock_page
from app.services.production_sales_service import (
    build_serialization_context,
    add_sale_payment,
    create_processing,
    create_production,
    create_reproduction,
    create_sale,
    production_sold_map,
    serialize_payment,
    serialize_processing,
    serialize_production,
    serialize_reproduction,
    serialize_sale,
    void_processing,
    void_sale,
)
from app.services.void_authorization import require_void_administrator
from app.services.task_engine import evaluate_automatic_tasks
from app.services.idempotency import (
    begin_creation_command,
    normalize_idempotency_key,
    record_creation_command,
    request_fingerprint,
)
from app.services.alert_engine import (
    evaluate_livestock_alerts_only,
    evaluate_production_sales_alerts_only,
)


router = APIRouter(
    prefix="/api/v1/production-sales",
    tags=["Production & Sales"],
)


def require_viewer(current_user: User = Depends(get_current_user)) -> User:
    if not has_permission(current_user, "production_sales:view"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view farm production and sales.",
        )
    return current_user


def require_editor(current_user: User = Depends(get_current_user)) -> User:
    if not has_permission(current_user, "production_sales:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage farm production and sales.",
        )
    return current_user


def _source_filter(column, source_type: str | None):
    normalized = str(source_type or "").strip().lower()
    if normalized == "crop":
        return func.lower(column) == "crop"
    if normalized == "livestock":
        return func.lower(column) == "livestock"
    return None


def _sale_source_filter(source_type: str | None):
    normalized = str(source_type or "").strip().lower()
    if normalized not in {"crop", "livestock", "inventory"}:
        return None
    return or_(
        func.lower(LivestockSale.source_type) == normalized,
        select(LivestockSaleItem.id)
        .where(
            LivestockSaleItem.sale_id == LivestockSale.id,
            func.lower(LivestockSaleItem.source_type) == normalized,
        )
        .exists(),
    )


def _text_match(search: str, *columns):
    needle = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(*(column.ilike(needle, escape="\\") for column in columns))


def _animal_match(parent_id, search: str):
    return select(Livestock.id).where(Livestock.id == parent_id,
        _text_match(search, Livestock.record_name, Livestock.animal_code)).exists()


def _crop_match(parent_id, search: str):
    return select(Crop.id).where(Crop.id == parent_id,
        _text_match(search, Crop.name, Crop.crop_code, Crop.field)).exists()


@router.get("/overview", response_model=OverviewResponse)
def overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    active_livestock = db.scalar(
        select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
            Livestock.is_archived == False,
            Livestock.lifecycle_status == "Active",
        )
    ) or 0
    harvest_ready_crops = db.scalar(
        select(func.count(Crop.id)).where(
            Crop.is_archived == False,
            Crop.status.in_(["Ready for Harvest", "Harvesting"]),
        )
    ) or 0
    breeding_records = db.scalar(select(func.count(LivestockReproductionRecord.id))) or 0
    production_records = db.scalar(select(func.count(LivestockProductionRecord.id))) or 0
    processing_records = db.scalar(
        select(func.count(LivestockProcessingRecord.id)).where(
            LivestockProcessingRecord.is_voided == False
        )
    ) or 0
    sales_records = db.scalar(
        select(func.count(LivestockSale.id)).where(LivestockSale.is_voided == False)
    ) or 0

    total_revenue, cash_collected, outstanding_balance = (
        float(value or 0) for value in db.execute(select(
            func.sum(LivestockSale.total_amount), func.sum(LivestockSale.amount_paid), func.sum(LivestockSale.balance_due)
        ).where(LivestockSale.is_voided == False)).one()
    )
    allocations = source_sales_totals(db)
    livestock_revenue, livestock_cash, livestock_receivable = allocations["livestock"]
    crop_revenue, crop_cash, crop_receivable = allocations["crop"]

    recent_production_records = list(
        db.scalars(
            select(LivestockProductionRecord)
            .order_by(
                LivestockProductionRecord.record_date.desc(),
                LivestockProductionRecord.id.desc(),
            )
            .limit(10)
        ).all()
    )
    recent_sales_records = list(
        db.scalars(
            select(LivestockSale)
            .where(LivestockSale.is_voided == False)
            .order_by(LivestockSale.sale_date.desc(), LivestockSale.id.desc())
            .limit(10)
        ).all()
    )
    context = build_serialization_context(db, recent_production_records + recent_sales_records)
    recent_sold = production_sold_map(db, [record.id for record in recent_production_records])
    recent_production = [
        serialize_production(db, record, sold_quantity=recent_sold.get(record.id, 0), context=context)
        for record in recent_production_records
    ]
    recent_sales = [serialize_sale(db, record, context=context) for record in recent_sales_records]

    stock_totals = production_stock_totals(db)

    return {
        "active_livestock": int(active_livestock),
        "harvest_ready_crops": int(harvest_ready_crops),
        "breeding_records": int(breeding_records),
        "production_records": int(production_records),
        "processing_records": int(processing_records),
        "sales_records": int(sales_records),
        "total_revenue": total_revenue,
        "cash_collected": cash_collected,
        "outstanding_balance": outstanding_balance,
        "livestock_revenue": livestock_revenue,
        "livestock_cash_collected": livestock_cash,
        "livestock_outstanding_balance": livestock_receivable,
        "crop_revenue": crop_revenue,
        "crop_cash_collected": crop_cash,
        "crop_outstanding_balance": crop_receivable,
        **stock_totals,
        "recent_production": recent_production,
        "recent_sales": recent_sales,
    }


@router.get("/stock")
def available_stock(
    kind: Annotated[str, Query(pattern="^(Production|Live Animal|Inventory)$")] = "Production",
    search: Annotated[str, Query(max_length=120)] = "",
    source_type: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    return stock_page(db, kind=kind, search=search, source_type=source_type, offset=offset, limit=limit)


@router.get("/reproduction", response_model=list[ReproductionResponse])
def list_reproduction(
    livestock_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    statement = select(LivestockReproductionRecord).order_by(
        LivestockReproductionRecord.event_date.desc(),
        LivestockReproductionRecord.id.desc(),
    )
    if livestock_id:
        statement = statement.where(LivestockReproductionRecord.livestock_id == livestock_id)
    if search and search.strip():
        statement = statement.where(or_(_animal_match(LivestockReproductionRecord.livestock_id, search),
            _text_match(search, LivestockReproductionRecord.record_type, LivestockReproductionRecord.reproductive_status)))
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    context = build_serialization_context(db, records)
    return [serialize_reproduction(db, record, context=context) for record in records]


@router.post("/reproduction", response_model=ReproductionResponse, status_code=status.HTTP_201_CREATED)
def add_reproduction(
    payload: ReproductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = normalize_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(payload)
    existing = begin_creation_command(db, idempotency_key=key, command_type="livestock-reproduction",
                                      request_hash=fingerprint, user_id=current_user.id)
    if existing is not None:
        record = db.get(LivestockReproductionRecord, existing.target_id)
        if record is None:
            raise HTTPException(409, "The saved reproduction retry target no longer exists.")
        return serialize_reproduction(db, record)
    result = create_reproduction(db, payload, current_user)
    record_creation_command(db, idempotency_key=key, command_type="livestock-reproduction",
                            request_hash=fingerprint, target_id=result["id"], user_id=current_user.id)
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    return result


@router.get("/production", response_model=list[ProductionResponse])
def list_production(
    livestock_id: int | None = Query(default=None, ge=1),
    crop_id: int | None = Query(default=None, ge=1),
    source_type: str | None = Query(default=None),
    available_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    statement = select(LivestockProductionRecord).order_by(
        LivestockProductionRecord.record_date.desc(),
        LivestockProductionRecord.id.desc(),
    )
    if livestock_id:
        statement = statement.where(LivestockProductionRecord.livestock_id == livestock_id)
    if crop_id:
        statement = statement.where(LivestockProductionRecord.crop_id == crop_id)
    source_clause = _source_filter(LivestockProductionRecord.source_type, source_type)
    if source_clause is not None:
        statement = statement.where(source_clause)
    if search and search.strip():
        statement = statement.where(or_(_animal_match(LivestockProductionRecord.livestock_id, search),
            _crop_match(LivestockProductionRecord.crop_id, search),
            _text_match(search, LivestockProductionRecord.output_type, LivestockProductionRecord.destination)))
    if available_only:
        availability = production_availability()
        statement = statement.join(availability, availability.c.production_id == LivestockProductionRecord.id).where(
            LivestockProductionRecord.track_sale_inventory == True, availability.c.available_quantity > 0,
        )
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    sold_map = production_sold_map(db, [record.id for record in records])
    context = build_serialization_context(db, records)
    serialized = [
        serialize_production(db, record, sold_quantity=sold_map.get(record.id, 0), context=context)
        for record in records
    ]
    return serialized


@router.post("/production", response_model=ProductionResponse, status_code=status.HTTP_201_CREATED)
def add_production(
    payload: ProductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = normalize_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(payload)
    existing = begin_creation_command(db, idempotency_key=key, command_type="production-output",
                                      request_hash=fingerprint, user_id=current_user.id)
    if existing is not None:
        record = db.get(LivestockProductionRecord, existing.target_id)
        if record is None:
            raise HTTPException(409, "The saved production retry target no longer exists.")
        return serialize_production(db, record)
    result = create_production(db, payload, current_user)
    record_creation_command(db, idempotency_key=key, command_type="production-output",
                            request_hash=fingerprint, target_id=result["id"], user_id=current_user.id)
    db.commit()
    return result


@router.get("/processing", response_model=list[ProcessingResponse])
def list_processing(
    livestock_id: int | None = Query(default=None, ge=1),
    include_voided: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    statement = select(LivestockProcessingRecord).order_by(
        LivestockProcessingRecord.processing_date.desc(),
        LivestockProcessingRecord.id.desc(),
    )
    if livestock_id:
        statement = statement.where(LivestockProcessingRecord.livestock_id == livestock_id)
    if not include_voided:
        statement = statement.where(LivestockProcessingRecord.is_voided == False)
    if search and search.strip():
        statement = statement.where(or_(_animal_match(LivestockProcessingRecord.livestock_id, search),
            _text_match(search, LivestockProcessingRecord.quality_grade)))
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    context = build_serialization_context(db, records)
    return [serialize_processing(db, record, context=context) for record in records]


@router.post("/processing", response_model=ProcessingResponse, status_code=status.HTTP_201_CREATED)
def add_processing(
    payload: ProcessingCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    key = normalize_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(payload)
    existing = begin_creation_command(
        db, idempotency_key=key, command_type="production-processing",
        request_hash=fingerprint, user_id=current_user.id,
    )
    if existing is not None:
        record = db.get(LivestockProcessingRecord, existing.target_id)
        if record is None:
            raise HTTPException(status_code=409, detail="The saved processing retry target no longer exists.")
        return serialize_processing(db, record)
    result = create_processing(db, payload, current_user)
    record_creation_command(
        db, idempotency_key=key, command_type="production-processing",
        request_hash=fingerprint, target_id=result["id"], user_id=current_user.id,
    )
    evaluate_automatic_tasks(db, commit=False)
    evaluate_livestock_alerts_only(db, commit=False)
    db.commit()
    return result


@router.post("/processing/{processing_id}/void", response_model=ProcessingResponse)
def void_processing_record(
    processing_id: int,
    payload: ProcessingVoidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    require_void_administrator(current_user)
    result = void_processing(db, processing_id, payload.reason, current_user)
    evaluate_automatic_tasks(db, commit=False)
    evaluate_livestock_alerts_only(db, commit=False)
    db.commit()
    return result


@router.get("/sales", response_model=list[SaleResponse])
def list_sales(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    source_type: str | None = Query(default=None),
    include_voided: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    statement = select(LivestockSale).order_by(
        LivestockSale.sale_date.desc(), LivestockSale.id.desc()
    )
    if not include_voided:
        statement = statement.where(LivestockSale.is_voided == False)
    if date_from:
        statement = statement.where(LivestockSale.sale_date >= date_from)
    if date_to:
        statement = statement.where(LivestockSale.sale_date <= date_to)
    source_clause = _sale_source_filter(source_type)
    if source_clause is not None:
        statement = statement.where(source_clause)
    if search and search.strip():
        matching_line = select(LivestockSaleItem.id).where(LivestockSaleItem.sale_id == LivestockSale.id,
            _text_match(search, LivestockSaleItem.product_type, LivestockSaleItem.source_name_snapshot,
                        LivestockSaleItem.source_code_snapshot)).exists()
        statement = statement.where(or_(matching_line, _animal_match(LivestockSale.livestock_id, search),
            _crop_match(LivestockSale.crop_id, search), _text_match(search, LivestockSale.sale_code,
                LivestockSale.product_type, LivestockSale.buyer_name, LivestockSale.payment_status)))
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    context = build_serialization_context(db, records)
    return [serialize_sale(db, record, context=context) for record in records]


@router.post("/sales", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def add_sale(
    payload: SaleCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    key = normalize_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(payload)
    existing = begin_creation_command(
        db, idempotency_key=key, command_type="production-sale",
        request_hash=fingerprint, user_id=current_user.id,
    )
    if existing is not None:
        record = db.get(LivestockSale, existing.target_id)
        if record is None:
            raise HTTPException(status_code=409, detail="The saved sale retry target no longer exists.")
        return serialize_sale(db, record)
    result = create_sale(db, payload, current_user)
    record_creation_command(
        db, idempotency_key=key, command_type="production-sale",
        request_hash=fingerprint, target_id=result["id"], user_id=current_user.id,
    )
    evaluate_automatic_tasks(db, commit=False)
    evaluate_production_sales_alerts_only(db, commit=False)
    if any(item["item_kind"] == "Live Animal" for item in result["items"]):
        evaluate_livestock_alerts_only(db, commit=False)
    db.commit()
    return result


@router.get("/sales/{sale_id}/payments", response_model=list[SalePaymentResponse])
def list_sale_payments(
    sale_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    sale = db.get(LivestockSale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale record not found.")
    records = list(
        db.scalars(
            select(LivestockSalePayment)
            .where(LivestockSalePayment.sale_id == sale_id)
            .order_by(LivestockSalePayment.payment_date.desc(), LivestockSalePayment.id.desc())
        ).all()
    )
    return [serialize_payment(record, db) for record in records]


@router.get("/sales/{sale_id}/receipt")
def get_sale_receipt(
    sale_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    sale = db.get(LivestockSale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale record not found.")
    payments = list(
        db.scalars(
            select(LivestockSalePayment)
            .where(LivestockSalePayment.sale_id == sale_id)
            .order_by(LivestockSalePayment.payment_date.asc(), LivestockSalePayment.id.asc())
        ).all()
    )
    return {
        "receipt_number": f"RCPT-{sale.sale_code}",
        "farm_name": "JoRoss Farm",
        "sale": serialize_sale(db, sale),
        "payments": [serialize_payment(item, db) for item in payments],
    }


@router.post("/sales/{sale_id}/payments", response_model=SalePaymentResult, status_code=status.HTTP_201_CREATED)
def record_sale_payment(
    sale_id: int,
    payload: SalePaymentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    key = normalize_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(payload)
    command_type = f"sale-payment:{sale_id}"
    existing = begin_creation_command(
        db, idempotency_key=key, command_type=command_type,
        request_hash=fingerprint, user_id=current_user.id,
    )
    if existing is not None:
        payment = db.get(LivestockSalePayment, existing.target_id)
        sale = db.get(LivestockSale, sale_id)
        if payment is None or sale is None or payment.sale_id != sale_id:
            raise HTTPException(status_code=409, detail="The saved payment retry target no longer exists.")
        return {"sale": serialize_sale(db, sale), "payment": serialize_payment(payment, db)}
    result = add_sale_payment(db, sale_id, payload, current_user)
    record_creation_command(
        db, idempotency_key=key, command_type=command_type,
        request_hash=fingerprint, target_id=result["payment"]["id"], user_id=current_user.id,
    )
    evaluate_production_sales_alerts_only(db, commit=False)
    db.commit()
    return result


@router.post("/sales/{sale_id}/void", response_model=SaleResponse)
def void_sale_record(
    sale_id: int,
    payload: SaleVoidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    require_void_administrator(current_user)
    result = void_sale(db, sale_id, payload.reason, current_user)
    evaluate_automatic_tasks(db, commit=False)
    evaluate_production_sales_alerts_only(db, commit=False)
    if any(item["item_kind"] == "Live Animal" for item in result["items"]):
        evaluate_livestock_alerts_only(db, commit=False)
    db.commit()
    return result
