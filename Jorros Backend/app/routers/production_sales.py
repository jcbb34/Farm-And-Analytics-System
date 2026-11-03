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
from app.services.production_sales_service import (
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

    def sale_sum(field):
        statement = select(func.coalesce(func.sum(field), 0)).where(
            LivestockSale.is_voided == False
        )
        return float(db.scalar(statement) or 0)

    total_revenue = sale_sum(LivestockSale.total_amount)
    cash_collected = sale_sum(LivestockSale.amount_paid)
    outstanding_balance = sale_sum(LivestockSale.balance_due)

    active_sales = list(
        db.scalars(select(LivestockSale).where(LivestockSale.is_voided == False)).all()
    )
    serialized_active_sales = [serialize_sale(db, sale) for sale in active_sales]

    def allocated_source_totals(source: str):
        gross = paid = balance = 0.0
        for sale in serialized_active_sales:
            invoice_total = float(sale["total_amount"] or 0)
            source_total = sum(
                float(item["line_total"] or 0)
                for item in sale["items"]
                if str(item["source_type"]).lower() == source
            )
            if source_total <= 0:
                continue
            ratio = source_total / invoice_total if invoice_total > 0 else 0
            gross += source_total
            paid += float(sale["amount_paid"] or 0) * ratio
            balance += float(sale["balance_due"] or 0) * ratio
        return gross, paid, balance

    livestock_revenue, livestock_cash, livestock_receivable = allocated_source_totals("livestock")
    crop_revenue, crop_cash, crop_receivable = allocated_source_totals("crop")

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
    recent_sold = production_sold_map(db, [record.id for record in recent_production_records])
    recent_production = [
        serialize_production(db, record, sold_quantity=recent_sold.get(record.id, 0))
        for record in recent_production_records
    ]
    recent_sales = [serialize_sale(db, record) for record in recent_sales_records]

    stock_records = list(
        db.scalars(
            select(LivestockProductionRecord).where(
                LivestockProductionRecord.track_sale_inventory == True
            )
        ).all()
    )
    sold_map = production_sold_map(db, [record.id for record in stock_records])
    eggs_available = 0.0
    meat_available_kg = 0.0
    milk_available_l = 0.0
    crop_available_kg = 0.0
    crop_product_lots = 0
    livestock_product_lots = 0
    for record in stock_records:
        available = max(0.0, float(record.quantity or 0) - float(sold_map.get(record.id, 0)))
        if available <= 0:
            continue
        source = str(record.source_type or ("Crop" if record.crop_id else "Livestock")).lower()
        output = str(record.output_type or "").lower()
        unit = str(record.unit or "").strip().lower()
        if source == "crop":
            crop_product_lots += 1
            if unit == "kg":
                crop_available_kg += available
        else:
            livestock_product_lots += 1
            if "egg" in output:
                eggs_available += available
            if "meat" in output and unit == "kg":
                meat_available_kg += available
            if "milk" in output and unit in {"l", "liter", "liters", "litre", "litres"}:
                milk_available_l += available

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
        "eggs_available": eggs_available,
        "meat_available_kg": meat_available_kg,
        "milk_available_l": milk_available_l,
        "crop_available_kg": crop_available_kg,
        "crop_product_lots": crop_product_lots,
        "livestock_product_lots": livestock_product_lots,
        "recent_production": recent_production,
        "recent_sales": recent_sales,
    }


@router.get("/reproduction", response_model=list[ReproductionResponse])
def list_reproduction(
    livestock_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    statement = select(LivestockReproductionRecord).order_by(
        LivestockReproductionRecord.event_date.desc(),
        LivestockReproductionRecord.id.desc(),
    )
    if livestock_id:
        statement = statement.where(LivestockReproductionRecord.livestock_id == livestock_id)
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    return [serialize_reproduction(db, record) for record in records]


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
    if available_only:
        # Filter before LIMIT/OFFSET. Filtering a page after it is loaded can
        # return empty pages while older saleable lots still exist.
        sold_lines = (
            select(func.coalesce(func.sum(LivestockSaleItem.quantity), 0))
            .join(LivestockSale, LivestockSale.id == LivestockSaleItem.sale_id)
            .where(
                LivestockSaleItem.production_record_id == LivestockProductionRecord.id,
                LivestockSale.is_voided == False,
            )
            .correlate(LivestockProductionRecord)
            .scalar_subquery()
        )
        legacy_sales = (
            select(func.coalesce(func.sum(LivestockSale.quantity), 0))
            .where(
                LivestockSale.production_record_id == LivestockProductionRecord.id,
                LivestockSale.is_voided == False,
                ~select(LivestockSaleItem.id)
                .where(LivestockSaleItem.sale_id == LivestockSale.id)
                .correlate(LivestockSale)
                .exists(),
            )
            .correlate(LivestockProductionRecord)
            .scalar_subquery()
        )
        statement = statement.where(
            LivestockProductionRecord.track_sale_inventory == True,
            LivestockProductionRecord.quantity > sold_lines + legacy_sales,
        )
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    sold_map = production_sold_map(db, [record.id for record in records])
    serialized = [
        serialize_production(db, record, sold_quantity=sold_map.get(record.id, 0))
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
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    return [serialize_processing(db, record) for record in records]


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
    records = list(db.scalars(statement.offset(offset).limit(limit)).all())
    return [serialize_sale(db, record) for record in records]


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
