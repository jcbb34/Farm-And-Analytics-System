"""Local Owner/Admin approval, bound to one record without switching sessions."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4
import jwt
from fastapi import HTTPException
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import joinedload
from app.core.config import settings
from app.core.dependencies import has_permission
from app.core.security import verify_password
from app.models import AuditLog, Employee, FarmActivity, ResourceUsage, User
from app.models.production_sale import LivestockProcessingRecord, LivestockSale
from app.models.void_operation import VoidOperation
from app.services.db_concurrency import acquire_transaction_lock

MODELS = {'task': FarmActivity, 'resource_usage': ResourceUsage, 'sale': LivestockSale, 'processing': LivestockProcessingRecord}

def owner_or_admin(user):
    return bool(user and user.status == 'Active' and user.role and user.role.is_active and has_permission(user, '*'))

def require_void_administrator(user):
    if not owner_or_admin(user):
        raise HTTPException(403, 'Only an Owner/System Admin can directly void records. Request Owner/Admin authorization instead.')

def _locked_record(db, action, record_id):
    model = MODELS[action]
    if action == 'task':
        acquire_transaction_lock(db, f'workforce-task-lifecycle:{record_id}')
    elif action == 'resource_usage':
        acquire_transaction_lock(db, f'resource-usage:{record_id}')
    statement = select(model).where(model.id == record_id)
    if db.get_bind().dialect.name == 'mssql':
        statement = statement.with_hint(model, 'WITH (UPDLOCK, ROWLOCK)', dialect_name='mssql')
    else:
        statement = statement.with_for_update()
    record = db.scalar(statement.execution_options(populate_existing=True))
    if record is None:
        raise HTTPException(404, 'Record not found.')
    return record

def _check_request_access(db, user, action, record):
    if owner_or_admin(user):
        return
    if action == 'task':
        from app.routers.workforce_handlers import _latest_submission
        if has_permission(user, 'workforce:review') or has_permission(user, 'workforce:manage'):
            return
        employee = db.scalar(select(Employee).where(Employee.login_user_id == user.id, Employee.is_archived == False))
        submission = _latest_submission(db, record.id)
        if has_permission(user, 'workforce:submit') and employee and employee.employment_status == 'Active' and submission and submission.employee_id == employee.id:
            return
    else:
        permission = ('crops:update' if record.module == 'Crop' else 'livestock:update') if action == 'resource_usage' else 'production_sales:update'
        if has_permission(user, permission):
            return
    raise HTTPException(403, 'You cannot request a void for this record.')

def _data(record):
    return {column.key: getattr(record, column.key) for column in inspect(record).mapper.column_attrs}

def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()

def _description(db, action, record):
    data = _data(record)
    if action == 'task':
        from app.routers.workforce_handlers import _latest_submission, _task_void_block_reason
        submission = _latest_submission(db, record.id)
        blocker = _task_void_block_reason(record, submission)
        if blocker:
            raise HTTPException(409, blocker)
        data['submission'] = _data(submission)
        usage = db.scalar(select(ResourceUsage).where(ResourceUsage.activity_id == record.id, ResourceUsage.task_posting_active == True, ResourceUsage.is_voided == False))
        if usage:
            data['usage'] = _data(usage)
        return record.name, (f'Restore {usage.quantity} {usage.unit} of {usage.item_name_snapshot}.' if usage else 'Void this approved work submission. No stock restoration is required.'), _digest(data)
    if record.is_voided:
        raise HTTPException(409, 'This record is already voided.')
    if action == 'resource_usage':
        if record.activity_id:
            raise HTTPException(409, 'Task-linked usage must be reversed through its approved task.')
        return f'{record.usage_type} usage #{record.id}', f'Restore {record.quantity} {record.unit} of {record.item_name_snapshot}.', _digest(data)
    if action == 'sale':
        return record.sale_code, 'Void the entire invoice and restore sold stock or animals where applicable. Payment history stays recorded.', _digest(data)
    return f'Processing #{record.id}', 'Restore processed animals only if none of the linked meat has been sold.', _digest(data)

def preview_void(db, user, action, record_id):
    record = _locked_record(db, action, record_id)
    _check_request_access(db, user, action, record)
    label, impact, fingerprint = _description(db, action, record)
    token = jwt.encode({'purpose': 'void_preview', 'sub': str(user.id), 'ver': int(user.auth_version or 0), 'action': action,
                        'record_id': record_id, 'fingerprint': fingerprint, 'jti': uuid4().hex,
                        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {'preview_token': token, 'label': label, 'impact': impact, 'expires_in': 300,
            'requires_owner_credentials': not owner_or_admin(user)}

def _authorize_owner(db, requester, payload, request):
    if owner_or_admin(requester):
        return requester
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ip = str(request.client.host if request.client else 'local')[:45]
    acquire_transaction_lock(db, f'void-auth-attempt:{requester.id}')
    acquire_transaction_lock(db, f'void-auth-device:{ip}')
    failed = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.event_type == 'void_auth_failed',
        AuditLog.created_at >= now - timedelta(minutes=15), or_(AuditLog.actor_user_id == requester.id, AuditLog.entity_id == ip))) or 0
    if failed >= 5:
        raise HTTPException(429, 'Too many failed authorization attempts. Try again after 15 minutes.', headers={'Retry-After': '900'})
    owner = db.scalar(select(User).options(joinedload(User.role)).where(func.lower(User.username) == str(payload.owner_username or '').strip().lower()).execution_options(populate_existing=True))
    try:
        valid = owner_or_admin(owner) and bool(payload.owner_password) and verify_password(payload.owner_password, owner.password_hash)
    except (ValueError, TypeError):
        valid = False
    from app.routers.auth import _verify_totp
    if not valid or not _verify_totp(owner, payload.otp_code):
        db.add(AuditLog(event_type='void_auth_failed', action='Owner/Admin void authorization failed', module='Security', entity_id=ip,
                        actor_user_id=requester.id, actor_name=requester.full_name, created_at=now, details='Authorization refused. No credentials were stored.'))
        db.commit()
        raise HTTPException(403, 'Owner/Admin authorization failed. Check the account, password and verification code if enabled.')
    return owner

def execute_authorized_void(db, requester, payload, request):
    try:
        claims = jwt.decode(payload.preview_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm],
                            options={'require': ['purpose', 'sub', 'ver', 'action', 'record_id', 'fingerprint', 'jti', 'exp']})
        if claims['purpose'] != 'void_preview' or claims['sub'] != str(requester.id) or claims['ver'] != int(requester.auth_version or 0) or claims['action'] not in MODELS:
            raise ValueError()
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(409, 'This void preview is invalid or expired. Reopen the authorization dialog.') from None
    reason = payload.reason.strip()
    request_hash = _digest({'requester': requester.id, 'action': claims['action'], 'record': claims['record_id'], 'reason': reason})
    acquire_transaction_lock(db, f'void-operation:{claims["jti"]}')
    # Check record access even on a retry; removing request permission takes effect immediately.
    record = _locked_record(db, claims['action'], int(claims['record_id']))
    _check_request_access(db, requester, claims['action'], record)
    authorizer = _authorize_owner(db, requester, payload, request)
    existing = db.scalar(select(VoidOperation).where(VoidOperation.operation_key == claims['jti']))
    if existing:
        if existing.request_hash != request_hash or existing.requester_user_id != requester.id:
            raise HTTPException(409, 'An authorization cannot be reused for a different void request.')
        return {'status': 'Voided', 'record_id': existing.record_id, 'action': existing.action, 'replayed': True}
    action, record_id = claims['action'], int(claims['record_id'])
    label, impact, fingerprint = _description(db, action, record)
    if fingerprint != claims['fingerprint']:
        raise HTTPException(409, 'The record changed after this preview. Reopen it and review the current record.')
    if action == 'task':
        from app.routers.workforce_handlers import _void_approved_task
        _void_approved_task(db, record_id, reason, authorizer)
    elif action == 'resource_usage':
        from app.services.resource_usage_service import void_usage
        void_usage(db, usage=record, reason=reason, current_user=authorizer)
    else:
        from app.services.production_sales_service import void_sale, void_processing
        result = (void_sale if action == 'sale' else void_processing)(db, record_id, reason, authorizer)
        from app.services.alert_engine import evaluate_livestock_alerts_only, evaluate_production_sales_alerts_only
        if action == 'processing' or any(item['item_kind'] == 'Live Animal' for item in result['items']):
            evaluate_livestock_alerts_only(db, commit=False)
        if action == 'sale':
            evaluate_production_sales_alerts_only(db, commit=False)
    db.add(VoidOperation(operation_key=claims['jti'], requester_user_id=requester.id, authorizer_user_id=authorizer.id,
                         action=action, record_id=record_id, request_hash=request_hash, reason=reason))
    db.add(AuditLog(event_type='audit', action='Owner/Admin authorized void', module='Security', record_name=label,
                    entity_id=f'{action}:{record_id}', actor_user_id=authorizer.id, actor_name=authorizer.full_name,
                    details=f'Requested by {requester.full_name} (user {requester.id}); authorized by {authorizer.full_name} (user {authorizer.id}). Reason: {reason}. {impact}'))
    from app.services.task_engine import evaluate_automatic_tasks
    evaluate_automatic_tasks(db, commit=False)
    db.commit()
    return {'status': 'Voided', 'record_id': record_id, 'action': action, 'replayed': False}
