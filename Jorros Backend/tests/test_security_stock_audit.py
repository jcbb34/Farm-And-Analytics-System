"""Real HTTP regressions for token separation, stock retries, and crop audit atomicity."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pyotp
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from app.core.config import settings
from app.core.security import (create_access_token, create_two_factor_challenge,
                               decode_access_token_claims, decode_two_factor_challenge, hash_password)
from app.models import (AuditLog, Crop, FarmActivity, FarmCreationCommand, InventoryItem,
                        InventoryStockRecord, Livestock, LivestockProductionRecord,
                        LivestockReproductionRecord, LivestockVaccinationRecord, User)
from app.models.livestock import LivestockPen
from app.routers import auth, events, production_sales


def test_two_factor_challenge_never_authorizes_api_requests(farm):
    farm.client.app.include_router(auth.router)
    farm.client.app.include_router(events.router)
    secret = pyotp.random_base32()
    with Session(farm.engine) as db:
        user = db.get(User, farm.users['manager'])
        user.password_hash = hash_password('synthetic-audit-password')
        user.two_factor_enabled = True
        user.two_factor_secret = secret
        db.commit()
    response = farm.client.post('/api/v1/auth/login', json={
        'username': 'monitoring.manager', 'password': 'synthetic-audit-password'})
    assert response.status_code == 200 and response.json()['requires_two_factor']
    challenge = response.json()['challenge_token']
    headers = {'Authorization': 'Bearer ' + challenge}
    for url in ['/api/v1/auth/me', '/api/v1/workforce/employees', '/api/v1/events/stream']:
        assert farm.client.get(url, headers=headers).status_code == 401
    assert decode_access_token_claims(challenge) is None

    totp = pyotp.TOTP(secret)
    now = datetime.now(timezone.utc)
    accepted = {totp.at(now + timedelta(seconds=n)) for n in (-30, 0, 30)}
    wrong = next(f'{n:06d}' for n in range(10) if f'{n:06d}' not in accepted)
    assert farm.client.post('/api/v1/auth/login/2fa', json={
        'challenge_token': challenge, 'otp_code': wrong}).status_code == 401
    verified = farm.client.post('/api/v1/auth/login/2fa', json={
        'challenge_token': challenge, 'otp_code': totp.now()})
    assert verified.status_code == 200, verified.text
    token = verified.json()['access_token']
    assert decode_two_factor_challenge(token) is None
    assert farm.client.get('/api/v1/workforce/employees', headers={
        'Authorization': 'Bearer ' + token}).status_code == 200
    assert farm.client.post('/api/v1/auth/login/2fa', json={
        'challenge_token': challenge, 'otp_code': totp.now()}).status_code == 401


@pytest.mark.parametrize('purpose', ['two_factor_login', 'refresh', '', None])
def test_signed_wrong_purpose_is_not_an_access_token(purpose):
    token = jwt.encode({'sub': '1', 'ver': 0, 'purpose': purpose,
                        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                       settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert decode_access_token_claims(token) is None


def test_existing_untyped_access_tokens_remain_compatible():
    token = jwt.encode({'sub': '42', 'ver': 3, 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                       settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert decode_access_token_claims(token) == (42, 3)
    current, _ = create_access_token(42, 3)
    assert decode_access_token_claims(current) == (42, 3)
    challenge, _ = create_two_factor_challenge(42, 3)
    assert decode_access_token_claims(challenge) is None


@pytest.fixture
def stock(farm):
    farm.client.app.include_router(production_sales.router)
    with Session(farm.engine) as db:
        animal = db.get(Livestock, farm.ids['Livestock'])
        animal.animal_type = 'Chicken'; animal.production_purpose = 'Egg Production'
        animal.female_quantity = 10; animal.male_quantity = 0; animal.unknown_sex_quantity = 0
        item = InventoryItem(item_code='RETRY-VAX', name='Synthetic Test Vaccine', category='Vaccine',
                             quantity=100, unit='test-units', supplier='Test', date_acquired=farm.today,
                             location='Test')
        pen = LivestockPen(name='Test offspring pen', purpose='Brooder', animal_type='Chicken', capacity=100)
        db.add_all([item, pen]); db.commit()
        farm.item_id, farm.pen_id = item.id, pen.id
    return farm


def entry(stock, operation):
    animal_id = stock.ids['Livestock']
    if operation == 'vaccination':
        return (f'/api/v1/livestock/{animal_id}/vaccination-records',
                {'vaccine': 'Synthetic Test Vaccine', 'date_administered': str(stock.today),
                 'status': 'Up to Date', 'inventory_item_id': stock.item_id, 'quantity_used': 2},
                LivestockVaccinationRecord, 'app.routers.livestock')
    if operation == 'production':
        return ('/api/v1/production-sales/production',
                {'livestock_id': animal_id, 'output_type': 'Eggs', 'record_date': str(stock.today),
                 'source_active_quantity': 10, 'gross_quantity': 5, 'quantity': 5, 'unit': 'pcs',
                 'track_sale_inventory': True}, LivestockProductionRecord, 'app.routers.production_sales')
    return ('/api/v1/production-sales/reproduction',
            {'livestock_id': animal_id, 'record_type': 'Hatch', 'event_date': str(stock.today),
             'offspring_count': 5, 'alive_offspring': 5, 'create_offspring_record': True,
             'offspring_average_weight_kg': 1, 'offspring_pen_id': stock.pen_id},
            LivestockReproductionRecord, 'app.routers.production_sales')


def assert_effect(stock, operation, count):
    with Session(stock.engine) as db:
        if operation == 'vaccination':
            assert float(db.get(InventoryItem, stock.item_id).quantity) == 100 - 2 * count
            assert db.scalar(select(func.count()).select_from(InventoryStockRecord)) == count
        elif operation == 'production':
            assert float(db.scalar(select(func.coalesce(func.sum(LivestockProductionRecord.quantity), 0)))) == 5 * count
        else:
            assert db.scalar(select(func.count()).select_from(Livestock)) == 1 + count
            assert db.scalar(select(func.coalesce(func.sum(Livestock.quantity), 0)).where(
                Livestock.origin_livestock_id == stock.ids['Livestock'])) == 5 * count


@pytest.mark.parametrize('operation', ['vaccination', 'production', 'reproduction'])
def test_identical_retry_returns_same_record_without_second_effect(stock, operation):
    url, payload, model, _ = entry(stock, operation)
    headers = {**stock.headers['manager'], 'Idempotency-Key': 'one-record-retry'}
    first = stock.client.post(url, json=payload, headers=headers)
    retry = stock.client.post(url, json=payload, headers=headers)
    assert first.status_code == retry.status_code == 201, (first.text, retry.text)
    assert first.json()['id'] == retry.json()['id']
    with Session(stock.engine) as db:
        assert db.scalar(select(func.count()).select_from(model)) == 1
        assert db.scalar(select(func.count()).select_from(FarmCreationCommand)) == 1
    assert_effect(stock, operation, 1)
    conflict = stock.client.post(url, json={**payload, 'notes': 'Different request'}, headers=headers)
    assert conflict.status_code == 409
    assert_effect(stock, operation, 1)


@pytest.mark.parametrize('operation', ['vaccination', 'production', 'reproduction'])
def test_failed_command_rolls_back_records_stock_and_retry_marker(stock, operation):
    url, payload, model, module = entry(stock, operation)
    headers = {**stock.headers['manager'], 'Idempotency-Key': 'failed-record-retry'}
    with patch(module + '.record_creation_command', side_effect=RuntimeError('Forced persistence failure')):
        with pytest.raises(RuntimeError):
            stock.client.post(url, json=payload, headers=headers)
    with Session(stock.engine) as db:
        assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(FarmCreationCommand)) == 0
    assert_effect(stock, operation, 0)
    assert stock.client.post(url, json=payload, headers=headers).status_code == 201
    assert_effect(stock, operation, 1)


@pytest.mark.parametrize('operation', ['vaccination', 'production', 'reproduction'])
def test_retry_still_requires_permission_and_same_actor(stock, operation):
    url, payload, _, _ = entry(stock, operation)
    headers = {**stock.headers['manager'], 'Idempotency-Key': 'owner-bound-retry'}
    assert stock.client.post(url, json=payload, headers=headers).status_code == 201
    assert stock.client.post(url, json=payload, headers={**stock.headers['worker'],
                             'Idempotency-Key': 'owner-bound-retry'}).status_code == 403
    with Session(stock.engine) as db:
        other = db.get(User, stock.users['other'])
        other.role_id = db.get(User, stock.users['manager']).role_id
        db.commit()
    assert stock.client.post(url, json=payload, headers={**stock.headers['other'],
                             'Idempotency-Key': 'owner-bound-retry'}).status_code == 409
    assert_effect(stock, operation, 1)


def test_crop_edit_has_server_actor_before_after_and_single_audit(farm):
    url = f'/api/v1/crops/{farm.ids["Crop"]}'
    response = farm.client.put(url, json={'field': 'New farm field'}, headers=farm.headers['manager'])
    assert response.status_code == 200, response.text
    with Session(farm.engine) as db:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.module == 'Crop')))
        assert len(rows) == 2 and {row.event_type for row in rows} == {'audit', 'timeline'}
        record = next(row for row in rows if row.event_type == 'audit')
        assert record.actor_user_id == farm.users['manager']
        assert record.entity_id == 'MON-CROP'
        assert json.loads(record.details)['changes']['field'] == {'before': 'Test field', 'after': 'New farm field'}
    # Saving an identical edit creates no duplicate change entry.
    assert farm.client.put(url, json={'field': 'New farm field'}, headers=farm.headers['manager']).status_code == 200
    with Session(farm.engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.module == 'Crop')) == 2
    assert farm.client.put(url, json={'field': 'Unauthorized'}, headers=farm.headers['worker']).status_code == 403


def test_crop_audit_failure_rolls_back_edit_and_generated_tasks(farm):
    with Session(farm.engine) as db:
        old_task_ids = set(db.scalars(select(FarmActivity.id)))
    with patch('app.routers.crops.record_crop_change', side_effect=RuntimeError('Forced audit failure')):
        with pytest.raises(RuntimeError):
            farm.client.put(f'/api/v1/crops/{farm.ids["Crop"]}', json={'field': 'Must roll back'},
                            headers=farm.headers['manager'])
    with Session(farm.engine) as db:
        assert db.get(Crop, farm.ids['Crop']).field == 'Test field'
        assert set(db.scalars(select(FarmActivity.id))) == old_task_ids
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_crop_create_retry_archive_restore_write_backend_history(farm):
    payload = {'name': 'New crop', 'variety': 'Test', 'field': 'Field B', 'area_hectares': 1,
               'quantity_planted': 50, 'planting_date': str(farm.today),
               'estimated_harvest': str(farm.today + timedelta(days=60))}
    headers = {**farm.headers['manager'], 'Idempotency-Key': 'crop-audit-create'}
    first = farm.client.post('/api/v1/crops', json=payload, headers=headers)
    retry = farm.client.post('/api/v1/crops', json=payload, headers=headers)
    assert first.status_code == retry.status_code == 201, (first.text, retry.text)
    crop_id = first.json()['id']; assert retry.json()['id'] == crop_id
    for action in ('archive', 'restore'):
        assert farm.client.post(f'/api/v1/crops/{crop_id}/{action}', json={'reason': 'Crop cycle closed'} if action == 'archive' else None, headers=farm.headers['manager']).status_code == 200
    with Session(farm.engine) as db:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.module == 'Crop', AuditLog.event_type.in_(['audit', 'timeline']))))
        assert len(rows) == 6
        assert {row.action for row in rows if row.event_type == 'audit'} == {
            'Created crop record', 'Archived crop record', 'Restored crop record'}
        assert not db.get(Crop, crop_id).is_archived
