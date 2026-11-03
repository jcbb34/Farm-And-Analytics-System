"""Shared archive policy and durable metadata in the existing audit ledger."""
import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import load_only

from app.core.database import Base
from app.core.dependencies import has_permission
from app.models import AuditLog, Crop, Livestock, InventoryItem, FarmReport, Employee, FarmActivity, User, TaskSubmission
from app.models.livestock import LivestockPen
from app.services.db_concurrency import acquire_transaction_lock

REGISTRY = {
    'Crop': (Crop, 'crop_code', 'name', 'crops:view', 'crops:archive', '/crops'),
    'Livestock': (Livestock, 'animal_code', 'record_name', 'livestock:view', 'livestock:archive', '/livestock'),
    'Inventory': (InventoryItem, 'item_code', 'name', 'inventory:view', 'inventory:archive', '/inventory'),
    'Report': (FarmReport, 'report_code', 'title', 'reports:view', 'reports:update', '/reports'),
    'Employee': (Employee, 'employee_code', 'full_name', 'workforce:manage', 'workforce:manage', '/task-management?tab=archives'),
    'Task': (FarmActivity, 'activity_code', 'name', 'workforce:manage', 'activities:update', '/task-management?tab=archives'),
    'User': (User, 'user_code', 'full_name', '*', '*', '/settings?section=archive'),
    'Pen': (LivestockPen, 'pen_code', 'name', 'livestock:view', 'livestock:update', '/livestock'),
}


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def config(module):
    if module not in REGISTRY:
        raise HTTPException(404, 'Archive module not found.')
    return REGISTRY[module]


def authorize(actor, module, *, write=False):
    row = config(module)
    if not has_permission(actor, row[4 if write else 3]):
        raise HTTPException(403, 'You do not have access to these archived records.')


def archived(module, record):
    return record.status == 'Archived' if module in {'Report', 'User'} else bool(record.is_archived)


def locked_record(db, module, record_id):
    model = config(module)[0]
    acquire_transaction_lock(db, f'archive:{module}:{record_id}')
    query = select(model).where(model.id == record_id).execution_options(populate_existing=True)
    if db.get_bind().dialect.name == 'mssql':
        query = query.with_hint(model, 'WITH (UPDLOCK, ROWLOCK)', dialect_name='mssql')
    record = db.scalar(query.with_for_update())
    if record is None:
        raise HTTPException(404, 'This record no longer exists. Return to Archived Records to see the current list.')
    return record


def archive_event(db, module, record, actor, action, reason, **extra):
    _, code_field, name_field, *_ = config(module)
    db.add(AuditLog(event_type='archive', action=action, module=module,
        entity_id=str(record.id), record_name=str(getattr(record, name_field, '') or getattr(record, code_field, '') or record.id)[:180],
        details=json.dumps({'reason': reason, **extra}, ensure_ascii=True),
        actor_user_id=actor.id, actor_name=(actor.full_name or actor.username)[:120], created_at=now(), icon='archive'))


def _pending_source_tasks(db, module, record_id):
    query = select(FarmActivity).where(FarmActivity.source_module == module,
        FarmActivity.source_record_id == record_id, FarmActivity.is_archived == False,
        FarmActivity.status.notin_(['Completed', 'Cancelled', 'Resolved', 'Voided'])).order_by(FarmActivity.id)
    return list(db.scalars(query).all())


def archive_impact(db, module, record_id, actor):
    authorize(actor, module, write=True)
    record = locked_record(db, module, record_id)
    tasks = _pending_source_tasks(db, module, record.id) if module in {'Crop', 'Livestock'} else []
    return {'already_archived': archived(module, record), 'pending_tasks': [
        {'id': task.id, 'code': task.activity_code, 'name': task.name, 'status': task.status} for task in tasks],
        'policy': 'Untouched Pending tasks are cancelled and archived together. Work already started or submitted must be resolved before archiving.',
        'quantity': float(record.quantity or 0) if module == 'Inventory' else None}


def change_archive_state(db, module, record_id, actor, *, archive, reason=None):
    authorize(actor, module, write=True)
    record = locked_record(db, module, record_id)
    if archived(module, record) == archive:
        return record  # retries never repeat task cancellation, audit or stock work
    if archive and (not reason or not reason.strip()):
        raise HTTPException(422, 'An archive reason is required.')
    reason = (reason or '').strip()
    if len(reason) > 500:
        raise HTTPException(422, 'Archive reason must be at most 500 characters.')
    if module == 'User' and actor.id == record.id:
        raise HTTPException(400, 'You cannot archive your own account.')
    before_status = getattr(record, 'status', None)
    before_crop = None
    if module == 'Crop':
        from app.services.crop_audit import crop_snapshot
        before_crop = crop_snapshot(record)
    cancelled = []
    if module == 'Inventory' and archive and Decimal(str(record.quantity or 0)) != 0:
        raise HTTPException(409, 'Inventory must have zero remaining stock before archiving. Record the authorized usage, transfer or adjustment first.')
    if module == 'Inventory' and archive and db.scalar(select(FarmActivity.id).where(
            FarmActivity.planned_inventory_item_id == record.id, FarmActivity.is_archived == False,
            FarmActivity.status.in_(['Pending', 'In Progress', 'Returned', 'Submitted for Review'])).limit(1)):
        raise HTTPException(409, 'Reassign open tasks to another inventory item before archiving this item.')
    if module == 'Pen' and archive and db.scalar(select(Livestock.id).where(Livestock.pen_id == record.id, Livestock.is_archived == False, Livestock.quantity > 0).limit(1)):
        raise HTTPException(409, 'Move the active livestock before archiving this pen.')
    if archive and module in {'Crop', 'Livestock'}:
        tasks = _pending_source_tasks(db, module, record.id)
        for task in tasks:
            acquire_transaction_lock(db, f'workforce-task-lifecycle:{task.id}')
            db.refresh(task, with_for_update=True)
        submitted = set(db.scalars(select(TaskSubmission.activity_id).where(TaskSubmission.activity_id.in_([task.id for task in tasks]))).all()) if tasks else set()
        blocked = [task.activity_code for task in tasks if not task.is_archived and (task.status != 'Pending' or task.id in submitted)]
        if blocked:
            raise HTTPException(409, 'Resolve started, returned or submitted work before archiving: ' + ', '.join(blocked[:8]))
        for task in tasks:
            if not task.is_archived and task.status == 'Pending':
                task.status = 'Cancelled'
                task.is_archived = True
                task.updated_at = now()
                archive_event(db, 'Task', task, actor, 'Archived', f'Source {module} archived: {reason}', source_archive=True)
                cancelled.append(task.activity_code)
    if module == 'Report':
        if archive:
            record.archived_from_status = record.status
            record.status = 'Archived'
        else:
            # Preserve every supported prior status, including failed/incomplete generation.
            # Missing legacy status must never silently approve a report.
            from app.schemas.reports import REPORT_STATUSES
            record.status = record.archived_from_status if record.archived_from_status in REPORT_STATUSES - {'Archived'} else 'Needs Review'
            record.archived_from_status = None
    elif module == 'User':
        if archive:
            record.auth_version = int(record.auth_version or 0) + 1
        if archive:
            if '*' in (record.permissions or []) and record.status == 'Active':
                others = db.scalars(select(User).where(User.status == 'Active', User.id != record.id)).all()
                if not any(has_permission(other, '*') and other.role and other.role.is_active for other in others):
                    raise HTTPException(409, 'The last active Owner/Admin cannot be archived.')
        record.status = 'Archived' if archive else 'Active'
    elif module == 'Employee':
        from app.routers.workforce_handlers import _flag_employee_open_tasks_for_reassignment, _release_employee_current_farm_assignments, _sync_linked_employee_login
        if archive:
            _flag_employee_open_tasks_for_reassignment(db, record.id)
            _release_employee_current_farm_assignments(db, record.id)
            record.archived_at, record.archived_by_user_id, record.archive_reason = now(), actor.id, reason
        record.is_archived, record.employment_status = archive, 'Inactive'
        _sync_linked_employee_login(db, record)
    else:
        if module == 'Task' and archive and record.status not in {'Completed', 'Cancelled', 'Resolved', 'Voided', 'Pending'}:
            raise HTTPException(409, 'Resolve started or submitted work before archiving this task.')
        if module == 'Task' and archive and record.status == 'Pending' and db.scalar(select(TaskSubmission.id).where(TaskSubmission.activity_id == record.id).limit(1)):
            raise HTTPException(409, 'Resolve the existing work submission before archiving this task.')
        if module == 'Task' and not archive:
            source = REGISTRY.get(record.source_module)
            parent = db.get(source[0], record.source_record_id) if source and record.source_record_id else None
            if parent is None and source and record.source_record_id:
                raise HTTPException(409, 'The linked source no longer exists. This task must remain archived.')
            if parent is not None and archived(record.source_module, parent):
                raise HTTPException(409, 'Restore the linked source record first.')
            if record.status == 'Cancelled':
                # A cancelled task remains cancelled; restoring is not reopening work.
                pass
        record.is_archived = archive
    if hasattr(record, 'updated_at'):
        record.updated_at = now()
    archive_event(db, module, record, actor, 'Archived' if archive else 'Restored', reason,
                  previous_status=before_status, cancelled_tasks=cancelled)
    if module == 'Crop':
        from app.services.crop_audit import record_crop_change
        record_crop_change(db, record, actor, action='Archived crop record' if archive else 'Restored crop record', before=before_crop)
    db.flush()
    return record


def latest_events(db, module=None):
    result = {}
    query = select(AuditLog).where(AuditLog.event_type == 'archive', AuditLog.action == 'Archived')
    if module:
        query = query.where(AuditLog.module == module)
    for event in db.scalars(query.order_by(AuditLog.id.desc())).all():
        result.setdefault((event.module, event.entity_id), event)
    return result


def serialize_record(db, module, record, actor, events):
    _, code_field, name_field, *_ = config(module)
    event = events.get((module, str(record.id)))
    meta = {}
    if event:
        try: meta = json.loads(event.details or '{}')
        except (ValueError, TypeError): pass
    timestamp = event.created_at if event else getattr(record, 'archived_at', None)
    actor_name = event.actor_name if event else None
    if not actor_name and getattr(record, 'archived_by_user_id', None):
        saved_actor = db.get(User, record.archived_by_user_id)
        actor_name = saved_actor.full_name if saved_actor else None
    fields = ('name', 'record_name', 'title', 'full_name', 'crop_code', 'animal_code', 'item_code', 'report_code', 'employee_code', 'activity_code', 'user_code',
              'field', 'variety', 'crop_type', 'animal_type', 'breed', 'quantity', 'unit', 'pen_location', 'status', 'employment_status', 'category', 'planting_date', 'date_acquired', 'location')
    details = {field: str(getattr(record, field)) for field in fields if getattr(record, field, None) is not None}
    if module == 'Report': details['status_before_archive'] = record.archived_from_status or 'Not recorded'
    code = getattr(record, code_field, None) or str(record.id)
    name = getattr(record, name_field, None) or code
    from zoneinfo import ZoneInfo
    timestamp_zone = timezone.utc if event else ZoneInfo('Asia/Manila')
    return {'id': f'{module.lower()}-{record.id}', 'sourceId': record.id, 'module': module, 'code': code,
            'recordName': f'{name} ({code})' if name != code else code,
            'reason': meta.get('reason') or getattr(record, 'archive_reason', None) or 'Not recorded',
            'archivedDate': timestamp.replace(tzinfo=timestamp_zone).isoformat() if timestamp else None,
            'archivedBy': actor_name or 'Not recorded', 'details': details,
            'canRestore': has_permission(actor, config(module)[4]), 'canDelete': has_permission(actor, '*')}


def list_archives(db, actor, *, module=None, search='', date_from=None, date_to=None, offset=0, limit=50, focus_id=None, counts_only=False):
    if module:
        authorize(actor, module)
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, 'Archive end date cannot precede start date.')
    events = {} if counts_only else latest_events(db, module)
    records, counts = [], {}
    for name, (model, *_rest) in REGISTRY.items():
        if not has_permission(actor, config(name)[3]): continue
        condition = model.status == 'Archived' if name in {'Report', 'User'} else model.is_archived == True
        if counts_only or (module and module != name):
            counts[name] = db.scalar(select(func.count()).select_from(model).where(condition)) or 0
            continue
        # Archive lists need display fields, never large report snapshots or credentials.
        fields = {'id', config(name)[1], config(name)[2], 'is_archived', 'archived_at', 'archived_by_user_id', 'archive_reason',
                  'name', 'record_name', 'title', 'full_name', 'crop_code', 'animal_code', 'item_code', 'report_code', 'employee_code', 'activity_code', 'user_code',
                  'field', 'variety', 'crop_type', 'animal_type', 'breed', 'quantity', 'unit', 'pen_location', 'status', 'employment_status', 'category', 'planting_date', 'date_acquired', 'location', 'archived_from_status'}
        columns = [getattr(model, field) for field in fields if hasattr(model, field)]
        rows = list(db.scalars(select(model).options(load_only(*columns)).where(condition)).all())
        counts[name] = len(rows)
        records.extend(serialize_record(db, name, record, actor, events) for record in rows)
    if counts_only:
        return {'items': [], 'total': counts.get(module, 0) if module else sum(counts.values()), 'offset': 0, 'limit': limit, 'counts': counts}
    if focus_id is not None and module:
        offset = 0
        records = [r for r in records if r['sourceId'] == focus_id]
        if not records:
            model = config(module)[0]
            if db.get(model, focus_id) is None:
                raise HTTPException(404, 'This archived record no longer exists.')
            raise HTTPException(409, 'This record has already been restored. It is no longer in the archive.')
    else:
        needle = (search or '').strip().casefold()
        if needle: records = [r for r in records if needle in ' '.join(str(r.get(key) or '') for key in ('recordName', 'module', 'reason', 'archivedBy')).casefold()]
        from zoneinfo import ZoneInfo
        def archive_date(row):
            return datetime.fromisoformat(row['archivedDate']).astimezone(ZoneInfo('Asia/Manila')).date() if row['archivedDate'] else None
        if date_from: records = [r for r in records if archive_date(r) and archive_date(r) >= date_from]
        if date_to: records = [r for r in records if archive_date(r) and archive_date(r) <= date_to]
    records.sort(key=lambda r: (datetime.fromisoformat(r['archivedDate']).timestamp() if r['archivedDate'] else float('-inf'), r['sourceId']), reverse=True)
    # A saved page can become empty after restores/deletions. Return the last
    # valid page so existing archived records are never mistaken for no records.
    if offset >= len(records):
        offset = max(0, (len(records) - 1) // limit) * limit
    return {'items': records[offset:offset+limit], 'total': len(records), 'offset': offset, 'limit': limit, 'counts': counts}


def permanent_delete(db, module, record_id, actor):
    if not has_permission(actor, '*'):
        raise HTTPException(403, 'Only Owner/Admin can permanently delete archived records.')
    record = locked_record(db, module, record_id)
    if not archived(module, record):
        raise HTTPException(409, 'Only archived records can be permanently deleted.')
    if module == 'Inventory' and Decimal(str(record.quantity or 0)) != 0:
        raise HTTPException(409, 'Inventory with remaining stock cannot be deleted.')
    if module == 'Report' and (record.archived_from_status != 'Draft' or record.approved_at or record.revision_of_report_id):
        raise HTTPException(409, 'Historical, approved and revised reports must be retained.')
    table_name = record.__tablename__
    if module in {'Crop', 'Livestock'} and db.scalar(select(FarmActivity.id).where(FarmActivity.source_module == module, FarmActivity.source_record_id == record.id).limit(1)):
        raise HTTPException(409, 'This record has linked task history and must remain archived.')
    # Do not detach or cascade-delete history. Check every incoming foreign key.
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == table_name:
                query = select(func.count()).select_from(table).where(fk.parent == record.id)
                if table.name == table_name: query = query.where(table.c.id != record.id)
                if db.scalar(query):
                    raise HTTPException(409, 'This record is linked to transactions or history and must remain archived.')
    if module in {'Crop', 'Livestock', 'Inventory', 'Employee', 'Task', 'User'}:
        # Snapshot references can outlive the source and do not use SQL FKs.
        code = str(getattr(record, config(module)[1], '') or '')
        for report in db.scalars(select(FarmReport)).all():
            try: snapshot = json.loads(report.snapshot_json or '{}')
            except (ValueError, TypeError): snapshot = {}
            keys = {'Crop': {'crop_id'}, 'Livestock': {'livestock_id', 'animal_id'}, 'Inventory': {'inventory_item_id', 'item_id'},
                    'Employee': {'employee_id'}, 'Task': {'task_id', 'activity_id'}, 'User': {'user_id', 'actor_user_id'}}[module]
            def mentions(value):
                if isinstance(value, dict):
                    return any((key in keys and str(child) == str(record.id)) or mentions(child) for key, child in value.items())
                if isinstance(value, list): return any(mentions(child) for child in value)
                return bool(code) and isinstance(value, str) and value == code
            if mentions(snapshot):
                raise HTTPException(409, 'This record is referenced by a historical report and must be retained.')
    archive_event(db, module, record, actor, 'Deleted', 'Unlinked archived record permanently deleted.')
    db.delete(record)
    db.flush()
