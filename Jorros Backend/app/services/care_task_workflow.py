from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_now_naive, farm_today
from app.models import (
    CareTemplate,
    CareTemplateStep,
    Crop,
    Employee,
    FarmActivity,
    InventoryItem,
    Livestock,
    User,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.services.code_counter_service import next_record_code
from app.services.growth_profile_service import estimated_biological_birth_anchor
from app.services.work_schedule_service import apply_schedule_aware_assignment
from app.services.task_assignment import (
    recalculate_task_reassignment,
    record_assignment_change,
)
from app.services.leave_coverage_service import apply_leave_coverage_to_task
from app.services.care_task_overlap import native_covered_occurrences, native_family_for_step


CARE_MODULES = {"Crop", "Livestock"}


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def target_type_value(module: str, target: Crop | Livestock) -> str:
    if module == "Crop":
        return str(getattr(target, "name", "") or "").strip()
    if module == "Livestock":
        return str(getattr(target, "animal_type", "") or "").strip()
    raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")


def target_base_date(module: str, target: Crop | Livestock) -> date:
    if module == "Crop":
        return target.planting_date
    if module == "Livestock":
        return target.date_acquired
    raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")


def target_display(module: str, target: Crop | Livestock) -> tuple[str, str, str]:
    if module == "Crop":
        return target.name, target.field, "/crops"
    if module == "Livestock":
        return target.record_name, (target.pen_location or "Jorros Farm"), "/livestock"
    raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")


def validate_care_template_for_target(
    db: Session,
    *,
    template_id: int,
    module: str,
    target: Crop | Livestock,
    require_active: bool = True,
) -> CareTemplate:
    if module not in CARE_MODULES:
        raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")

    template = db.get(CareTemplate, int(template_id))
    if template is None or (require_active and not template.is_active):
        raise HTTPException(status_code=404, detail="Active care template not found.")
    if template.module != module:
        raise HTTPException(
            status_code=400,
            detail="Care template module does not match the target module.",
        )

    if require_active and getattr(template, "status", "Published") not in {"Published", "Superseded"}:
        raise HTTPException(status_code=400, detail="Only published care-protocol versions can generate operational tasks.")
    today = farm_today()
    if template.effective_from and today < template.effective_from:
        raise HTTPException(status_code=400, detail="This care-protocol version is not effective yet.")
    if template.effective_to and today > template.effective_to:
        raise HTTPException(status_code=400, detail="This care-protocol version is outside its effective dates.")

    expected = _normalize(template.target_type)
    actual = _normalize(target_type_value(module, target))
    if expected and expected != actual:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Care protocol target type '{template.target_type}' does not match "
                f"this {module.lower()} target '{target_type_value(module, target)}'."
            ),
        )

    qualifiers = []
    if module == "Crop":
        qualifiers = [
            ("variety", template.target_variety, getattr(target, "variety", None)),
            ("growth stage", template.growth_stage, getattr(target, "growth_stage", None)),
        ]
    else:
        qualifiers = [
            ("breed", template.target_breed, getattr(target, "breed", None)),
            ("production purpose", template.production_purpose, getattr(target, "production_purpose", None)),
            ("growth stage", template.growth_stage, getattr(target, "growth_status", None)),
        ]
    for label, expected_value, actual_value in qualifiers:
        if _normalize(expected_value) and _normalize(expected_value) != _normalize(actual_value):
            raise HTTPException(
                status_code=400,
                detail=f"Care protocol {label} '{expected_value}' does not match target value '{actual_value}'.",
            )
    return template


def _assignable_employee(db: Session, employee_id: int | None) -> Employee | None:
    if not employee_id:
        return None
    employee = db.get(Employee, int(employee_id))
    if employee is None or employee.is_archived:
        raise HTTPException(status_code=404, detail="Employee profile not found.")
    if employee.employment_status != "Active":
        raise HTTPException(
            status_code=400,
            detail=(
                f"{employee.full_name} is {employee.employment_status.lower()} "
                "and cannot receive new assignments."
            ),
        )
    return employee


def _next_activity_code(db: Session) -> str:
    return next_record_code(
        db,
        namespace="activity",
        prefix="ACT",
        seed_model=FarmActivity,
        code_column=FarmActivity.activity_code,
    )


def _usage_type(module: str, item: InventoryItem | None, step: CareTemplateStep) -> str | None:
    if item is None:
        return None
    category = _normalize(item.category)
    task_text = _normalize(" ".join([step.title, step.category, step.instructions or ""]))
    if module == "Crop":
        if category in {"seed", "seeds"}:
            return "Seed"
        if category in {"fertilizer", "fertilizers"}:
            return "Fertilizer"
        if category in {"pesticide", "pesticides"}:
            return "Pesticide"
        if category in {"herbicide", "herbicides"}:
            return "Herbicide"
        return "Other"
    if category in {"livestock feed", "animal feed", "feed", "feeds"}:
        return "Feed"
    if category in {"vaccine", "vaccines"}:
        return "Vaccine"
    if category in {"vitamin", "vitamins", "supplement", "supplements"}:
        return "Vitamin / Supplement"
    if category in {"medicine", "medicines", "animal medicine", "livestock medicine"}:
        return "Vaccine" if "vaccin" in task_text or "booster" in task_text else "Medicine"
    if category in {"cleaning supplies", "cleaning supply", "sanitation supply", "sanitation supplies"}:
        return "Disinfectant" if "disinfect" in task_text else "Sanitation Supply"
    if category in {"treatment supply", "treatment supplies", "medical supply", "medical supplies"}:
        return "Treatment Supply"
    if category in {"disinfectant", "disinfectants"}:
        return "Disinfectant"
    return "Other"


def _resource_for_step(db: Session, step: CareTemplateStep) -> InventoryItem | None:
    """Resolve a current inventory item without permanently binding a protocol to a lot.

    inventory_item_id remains supported for migrated legacy templates only. New
    protocols should use resource_product_name and/or resource_category.
    """
    if step.inventory_item_id:
        item = db.get(InventoryItem, step.inventory_item_id)
        if item is None or item.is_archived:
            raise HTTPException(status_code=400, detail=f"Care step '{step.title}' references a missing or archived legacy Inventory resource.")
        return item

    product = _normalize(step.resource_product_name)
    category = _normalize(step.resource_category)
    if not product and not category:
        return None

    stmt = select(InventoryItem).where(InventoryItem.is_archived == False)
    items = list(db.scalars(stmt.order_by(InventoryItem.expiration_date, InventoryItem.date_acquired, InventoryItem.id)).all())
    for item in items:
        if product and _normalize(item.name) != product:
            continue
        if category and _normalize(item.category) != category:
            continue
        if step.planned_unit and _normalize(step.planned_unit) != _normalize(item.unit):
            continue
        return item
    detail = step.resource_product_name or step.resource_category or "resource"
    raise HTTPException(status_code=400, detail=f"No active Inventory item matches care-protocol resource '{detail}' for step '{step.title}'.")


def care_source_key(*, module: str, target_id: int, template_id: int, step_id: int, base_date: date, occurrence_index: int = 0, task_date: date | None = None) -> str:
    base = f"care:{module.lower()}:{target_id}:{template_id}:{step_id}:{base_date.isoformat()}"
    if occurrence_index > 0 or task_date is not None:
        return f"{base}:r{occurrence_index}:{(task_date or base_date).isoformat()}"
    return base


def _anchor_date(module: str, target: Crop | Livestock, step: CareTemplateStep, default_base: date, previous_dates: dict[int, date]) -> date | None:
    anchor = (step.timing_anchor or "base_date").strip().lower()
    if anchor in {"base_date", "planting_date"}:
        if anchor == "planting_date" and module != "Crop":
            return None
        return target.planting_date if module == "Crop" else default_base
    if anchor == "birth_date":
        return estimated_biological_birth_anchor(target) if module == "Livestock" else None
    if anchor == "acquisition_date":
        return getattr(target, "date_acquired", None) if module == "Livestock" else None
    if anchor == "age_window":
        biological_birth = estimated_biological_birth_anchor(target) if module == "Livestock" else None
        return (biological_birth + timedelta(days=int(step.age_start_days or 0))) if biological_birth else None
    if anchor == "stage":
        return farm_today()
    if anchor == "previous_step":
        return previous_dates.get(int(step.previous_step_sequence or 0))
    return default_base


def _desired_occurrences(module: str, target: Crop | Livestock, template: CareTemplate, steps: list[CareTemplateStep], base_date: date) -> list[tuple[CareTemplateStep, date, int]]:
    desired: list[tuple[CareTemplateStep, date, int]] = []
    previous_dates: dict[int, date] = {}
    for step in steps:
        anchor = _anchor_date(module, target, step, base_date, previous_dates)
        if anchor is None:
            continue
        first_date = anchor + timedelta(days=int(step.offset_days or 0))
        if step.timing_anchor == "age_window" and module == "Livestock":
            biological_birth = estimated_biological_birth_anchor(target)
            if biological_birth is None:
                continue
            window_end = (
                biological_birth + timedelta(days=int(step.age_end_days))
                if step.age_end_days is not None else None
            )
            today = farm_today()
            if window_end is not None and today > window_end:
                # Acquired/transferred animals do not receive clearly expired
                # early-life care steps.
                continue
            if first_date < today:
                # If the biological-age window is still active, schedule the
                # currently-applicable step now instead of backdating it.
                first_date = today
        previous_dates[step.sequence_number] = first_date
        count = int(step.recurrence_occurrences or 1)
        interval = int(step.recurrence_interval_days or 0)
        for idx in range(count):
            task_date = first_date + timedelta(days=(interval * idx if idx else 0))
            if template.effective_from and task_date < template.effective_from:
                continue
            if template.effective_to and task_date > template.effective_to:
                continue
            desired.append((step, task_date, idx))
    return desired


def _task_description(template: CareTemplate, step: CareTemplateStep) -> str:
    parts = [f"Generated from care protocol {template.name} v{template.version}."]
    if step.dose_basis:
        parts.append(f"Dose basis: {step.dose_basis.replace('_', ' ')}.")
    if step.safety_notes:
        parts.append(f"Safety: {step.safety_notes}")
    if step.withdrawal_interval_days is not None:
        parts.append(f"Withdrawal interval: {step.withdrawal_interval_days} day(s); follow the approved product label/veterinarian protocol.")
    if step.preharvest_interval_days is not None:
        parts.append(f"Pre-harvest interval: {step.preharvest_interval_days} day(s); follow the approved product label/agriculturist protocol.")
    return " ".join(parts)


def generate_care_tasks_for_target(db: Session, *, module: str, target: Crop | Livestock, template: CareTemplate, current_user: User, base_date: date | None = None, employee_id: int | None = None, backup_employee_id: int | None = None, time_sensitive: bool = False, controlled_rescheduling: bool = False, max_delay_minutes: int | None = None, future_only: bool = False) -> list[FarmActivity]:
    """Generate version-pinned protocol occurrences without committing."""
    if module == "Crop" and (target.is_archived or target.status in {"Harvested", "Failed"}):
        raise HTTPException(status_code=400, detail="Completed, failed, or archived crop cycles cannot generate new care tasks.")
    validate_care_template_for_target(db, template_id=template.id, module=module, target=target, require_active=True)
    base_date = base_date or target_base_date(module, target) or farm_today()
    target_name, location, source_path = target_display(module, target)
    selected_employee_id = employee_id or getattr(target, "assigned_employee_id", None)
    employee = _assignable_employee(db, selected_employee_id)
    acquire_transaction_lock(db, f"care-task-generation:{module.lower()}:{target.id}:{template.id}:{base_date.isoformat()}")
    steps = list(db.scalars(select(CareTemplateStep).where(CareTemplateStep.template_id == template.id).order_by(CareTemplateStep.sequence_number)).all())
    generated: list[FarmActivity] = []
    today = farm_today()
    desired = _desired_occurrences(module, target, template, steps, base_date)
    native_covered = native_covered_occurrences(db, module=module, target=target, occurrences=desired)
    for step, task_date, idx in desired:
        if module == "Livestock" and task_date < today:
            # Never backfill expired age-based care for newly acquired adults.
            continue
        if future_only and task_date <= today:
            continue
        source_key = care_source_key(module=module, target_id=target.id, template_id=template.id, step_id=step.id, base_date=base_date, occurrence_index=idx if (step.recurrence_occurrences or 1) > 1 else 0, task_date=task_date if (step.recurrence_occurrences or 1) > 1 else None)
        existing = db.scalar(select(FarmActivity).where(FarmActivity.source_key == source_key))
        family = native_family_for_step(module, step.category, step.title)
        if family and (family, task_date) in native_covered:
            if existing is not None and existing.status == "Pending" and not existing.is_archived:
                existing.status = "Resolved"
                existing.completed_at = None
                existing.updated_at = farm_now_naive()
            continue
        if existing is not None:
            if existing.status != "Pending" or existing.is_archived:
                # Reconciliation never reactivates or reassigns submitted,
                # started, completed, or deliberately resolved history.
                generated.append(existing)
                continue
            if existing.default_employee_id is None and existing.assignment_source == "automatic_default":
                existing.default_employee_id = selected_employee_id
            if existing.assignment_source in {"automatic_default", "Rest-Day Coverage"}:
                apply_leave_coverage_to_task(
                    db, existing, default_employee_id=existing.default_employee_id or selected_employee_id,
                )
                if existing.assignment_source != "Leave Coverage":
                    apply_schedule_aware_assignment(
                        db, existing, default_employee_id=existing.default_employee_id or selected_employee_id,
                        actor_user_id=current_user.id, actor_name=current_user.full_name,
                    )
            recalculate_task_reassignment(db, existing)
            generated.append(existing)
            continue
        resource_item = _resource_for_step(db, step)
        task = FarmActivity(
            activity_code=_next_activity_code(db), name=step.title, category=step.category,
            related_to=target_name, location=location, description=_task_description(template, step), instructions=step.instructions,
            activity_date=task_date, start_time=time(8, 0), assigned_by=current_user.full_name,
            assigned_to=employee.full_name if employee else "Unassigned", assigned_employee_id=employee.id if employee else None,
            default_employee_id=selected_employee_id, backup_employee_id=backup_employee_id,
            time_sensitive=bool(time_sensitive), controlled_rescheduling=bool(controlled_rescheduling),
            max_delay_minutes=max_delay_minutes,
            assignment_source="automatic_default", status="Pending", priority=step.priority,
            requires_review=True, requires_evidence=step.requires_evidence,
            planned_quantity=step.planned_quantity,
            planned_unit=resource_item.unit if resource_item is not None else step.planned_unit,
            planned_inventory_item_id=resource_item.id if resource_item is not None else None,
            planned_usage_type=_usage_type(module, resource_item, step), is_automatic=True,
            source_module=module, source_type="care_template_step", source_record_id=target.id,
            source_detail_id=step.id, source_code=template.template_code,
            source_protocol_family_code=template.protocol_family_code, source_protocol_version=template.version,
            source_path=source_path, source_key=source_key, created_by_user_id=current_user.id,
        )
        db.add(task); db.flush()
        if employee is not None:
            record_assignment_change(db, task, old_employee_id=None, new_employee_id=employee.id,
                assignment_source="automatic_default", actor_user_id=current_user.id, actor_name=current_user.full_name,
                reason=f"Initial automatic assignment from the {module.lower()} record default employee during care-protocol generation.")
        apply_leave_coverage_to_task(
            db, task, default_employee_id=selected_employee_id,
        )
        if task.assignment_source != "Leave Coverage":
            apply_schedule_aware_assignment(
                db, task, default_employee_id=selected_employee_id,
                actor_user_id=current_user.id, actor_name=current_user.full_name,
            )
        recalculate_task_reassignment(db, task)
        generated.append(task)
    return generated


def future_pending_care_tasks(db: Session, *, module: str, target_id: int, template_id: int | None = None) -> list[FarmActivity]:
    stmt = select(FarmActivity).where(FarmActivity.is_automatic == True, FarmActivity.is_archived == False,
        FarmActivity.source_module == module, FarmActivity.source_type == "care_template_step",
        FarmActivity.source_record_id == int(target_id), FarmActivity.status == "Pending", FarmActivity.activity_date > farm_today())
    if template_id is not None:
        stmt = stmt.where(FarmActivity.source_key.like(f"care:{module.lower()}:{int(target_id)}:{int(template_id)}:%"))
    return list(db.scalars(stmt.order_by(FarmActivity.activity_date, FarmActivity.id)).all())


def resolve_future_pending_care_tasks(db: Session, *, module: str, target_id: int, template_id: int | None = None) -> int:
    tasks = future_pending_care_tasks(db, module=module, target_id=target_id, template_id=template_id)
    now = farm_now_naive()
    for task in tasks:
        task.status = "Resolved"; task.completed_at = None; task.updated_at = now
    return len(tasks)


def reconcile_same_template_future_schedule(db: Session, *, module: str, target: Crop | Livestock, template: CareTemplate, current_user: User, base_date: date | None = None, employee_id: int | None = None, backup_employee_id: int | None = None, time_sensitive: bool | None = None, controlled_rescheduling: bool | None = None, max_delay_minutes: int | None = None) -> list[FarmActivity]:
    """Reconcile only future Pending occurrences for the same protocol version.

    Pending rows are updated in place where a corresponding future occurrence
    still exists. Submitted/in-progress/completed/resolved/archived history is
    never rewritten.
    """
    if module == "Crop" and (target.is_archived or target.status in {"Harvested", "Failed"}):
        raise HTTPException(status_code=400, detail="Completed, failed, or archived crop cycles cannot regenerate care tasks.")
    validate_care_template_for_target(db, template_id=template.id, module=module, target=target, require_active=True)
    base_date = base_date or target_base_date(module, target)
    steps = list(db.scalars(select(CareTemplateStep).where(CareTemplateStep.template_id == template.id).order_by(CareTemplateStep.sequence_number)).all())
    desired = _desired_occurrences(module, target, template, steps, base_date)
    native_covered = native_covered_occurrences(db, module=module, target=target, occurrences=desired)
    today = farm_today(); now = farm_now_naive()
    target_name, location, source_path = target_display(module, target)

    desired_by_step: dict[int, list[tuple[str, CareTemplateStep, date]]] = {}
    for step, task_date, idx in desired:
        if task_date <= today:
            continue
        family = native_family_for_step(module, step.category, step.title)
        if family and (family, task_date) in native_covered:
            continue
        recurring = (step.recurrence_occurrences or 1) > 1
        key = care_source_key(
            module=module, target_id=target.id, template_id=template.id,
            step_id=step.id, base_date=base_date,
            occurrence_index=idx if recurring else 0,
            task_date=task_date if recurring else None,
        )
        desired_by_step.setdefault(step.id, []).append((key, step, task_date))

    existing = future_pending_care_tasks(db, module=module, target_id=target.id, template_id=template.id)
    policy_seed = existing[0] if existing else None
    policy_default_employee_id = employee_id or (policy_seed.default_employee_id if policy_seed else None) or getattr(target, "assigned_employee_id", None)
    policy_backup_employee_id = backup_employee_id if backup_employee_id is not None else (policy_seed.backup_employee_id if policy_seed else None)
    policy_time_sensitive = bool(time_sensitive if time_sensitive is not None else (policy_seed.time_sensitive if policy_seed else False))
    policy_controlled_rescheduling = bool(controlled_rescheduling if controlled_rescheduling is not None else (policy_seed.controlled_rescheduling if policy_seed else False))
    policy_max_delay_minutes = max_delay_minutes if max_delay_minutes is not None else (policy_seed.max_delay_minutes if policy_seed else None)
    existing_by_step: dict[int, list[FarmActivity]] = {}
    for task in existing:
        if task.source_detail_id:
            existing_by_step.setdefault(int(task.source_detail_id), []).append(task)
        else:
            task.status = "Resolved"; task.completed_at = None; task.updated_at = now

    kept: list[FarmActivity] = []
    used_keys: set[str] = set()
    for step in steps:
        desired_rows = desired_by_step.get(step.id, [])
        current_rows = sorted(existing_by_step.get(step.id, []), key=lambda row: (row.activity_date, row.id))
        for index, task in enumerate(current_rows):
            if index >= len(desired_rows):
                task.status = "Resolved"; task.completed_at = None; task.updated_at = now
                continue
            expected_key, desired_step, expected_date = desired_rows[index]
            conflict = db.scalar(select(FarmActivity).where(FarmActivity.source_key == expected_key, FarmActivity.id != task.id))
            if conflict is not None:
                task.status = "Resolved"; task.completed_at = None; task.updated_at = now
                continue
            resource_item = _resource_for_step(db, desired_step)
            task.name=desired_step.title; task.category=desired_step.category; task.related_to=target_name; task.location=location
            task.description=_task_description(template, desired_step); task.instructions=desired_step.instructions; task.activity_date=expected_date
            task.priority=desired_step.priority; task.requires_review=True; task.requires_evidence=desired_step.requires_evidence
            task.planned_quantity=desired_step.planned_quantity; task.planned_unit=resource_item.unit if resource_item else desired_step.planned_unit
            task.planned_inventory_item_id=resource_item.id if resource_item else None; task.planned_usage_type=_usage_type(module, resource_item, desired_step)
            task.source_code=template.template_code; task.source_protocol_family_code=template.protocol_family_code; task.source_protocol_version=template.version
            task.source_path=source_path; task.source_key=expected_key; task.updated_at=now
            if task.default_employee_id is None:
                task.default_employee_id = policy_default_employee_id
            if task.backup_employee_id is None:
                task.backup_employee_id = policy_backup_employee_id
            task.time_sensitive = policy_time_sensitive
            task.controlled_rescheduling = policy_controlled_rescheduling
            task.max_delay_minutes = policy_max_delay_minutes
            if task.assignment_source in {"automatic_default", "Rest-Day Coverage"}:
                apply_leave_coverage_to_task(
                    db, task, default_employee_id=task.default_employee_id or policy_default_employee_id,
                )
                if task.assignment_source != "Leave Coverage":
                    apply_schedule_aware_assignment(
                        db, task, default_employee_id=task.default_employee_id or policy_default_employee_id,
                        actor_user_id=current_user.id, actor_name=current_user.full_name,
                    )
            recalculate_task_reassignment(db, task); kept.append(task); used_keys.add(expected_key)

    missing_keys = {
        key for rows in desired_by_step.values() for key, _, _ in rows if key not in used_keys
    }
    if missing_keys:
        generated = generate_care_tasks_for_target(
            db, module=module, target=target, template=template,
            current_user=current_user, base_date=base_date,
            employee_id=policy_default_employee_id, backup_employee_id=policy_backup_employee_id,
            time_sensitive=policy_time_sensitive, controlled_rescheduling=policy_controlled_rescheduling,
            max_delay_minutes=policy_max_delay_minutes, future_only=True,
        )
        kept.extend(task for task in generated if task.source_key in missing_keys)
    return kept
