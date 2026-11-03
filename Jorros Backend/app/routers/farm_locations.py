"""Physical farm locations, separate from postal/address reference data."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import has_permission
from app.models import Crop, InventoryItem, Livestock, LivestockPen, FarmActivity, User
from app.routers.auth import get_current_user
from app.services.event_planning import event_domain, EQUIPMENT_CATEGORIES
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/farm-locations", tags=["Farm locations"])


@router.get("")
def location_choices(
    context: Literal["crops", "inventory", "events"] = Query("events"),
    event_type: str | None = Query(None, max_length=80),
    source_module: Literal["Crop", "Livestock", "Inventory"] | None = None,
    source_record_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    permission = {
        "crops": "crops:view",
        "inventory": "inventory:view",
        "events": "activities:view",
    }[context]
    if not has_permission(user, permission):
        raise HTTPException(403, f"Permission required: {permission}.")
    domain = event_domain(event_type) if context == "events" else None
    if context == "events" and domain == "General" and source_module:
        domain = source_module
    include_crop = context == "crops" or (
        context == "events" and domain in {"Crop", "General"}
    )
    include_inventory = context == "inventory" or (
        context == "events" and domain in {"Inventory", "Equipment", "General"}
    )
    include_livestock = context == "events" and domain in {"Livestock", "General"}
    sources = []
    if include_crop:
        statement = select(Crop.field).where(Crop.is_archived == False)
        if context == "events" and source_record_id and domain == "Crop":
            statement = statement.where(Crop.id == source_record_id)
        sources.append(statement.distinct().order_by(Crop.field))
    if include_inventory:
        statement = select(InventoryItem.location).where(
            InventoryItem.is_archived == False
        )
        if (
            context == "events"
            and source_record_id
            and domain in {"Inventory", "Equipment"}
        ):
            statement = statement.where(InventoryItem.id == source_record_id)
        if domain == "Equipment":
            statement = statement.where(
                func.lower(func.ltrim(func.rtrim(InventoryItem.category))).in_(
                    EQUIPMENT_CATEGORIES
                )
            )
        sources.append(statement.distinct().order_by(InventoryItem.location))
    if include_livestock:
        statement = select(Livestock.pen_location).where(Livestock.is_archived == False)
        if source_record_id and domain == "Livestock":
            statement = statement.where(Livestock.id == source_record_id)
        sources.append(statement.distinct().order_by(Livestock.pen_location))
        if not source_record_id:
            sources.append(
                select(LivestockPen.name)
                .where(
                    LivestockPen.is_archived == False, LivestockPen.status == "Active"
                )
                .distinct()
                .order_by(LivestockPen.name)
            )
    if context == "events" and domain == "General":
        sources.extend(
            [
                select(FarmActivity.location)
                .where(FarmActivity.is_archived == False)
                .distinct()
                .order_by(FarmActivity.location),
            ]
        )
    names = {}
    for stmt in sources:
        for raw in db.scalars(stmt).all():
            name = " ".join(str(raw or "").split())
            if name and name.casefold() not in {
                "unassigned",
                "not specified",
                "not recorded",
                "—",
            }:
                names.setdefault(name.casefold(), name)
    return {
        "items": sorted(names.values(), key=str.casefold),
        "domain": (
            domain
            if context == "events"
            else "Crop" if context == "crops" else "Inventory"
        ),
    }
