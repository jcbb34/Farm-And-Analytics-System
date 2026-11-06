"""Temporary sessions and idle leases, with isolated records and real HTTP auth."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models import Role, User
from app.routers import auth
from app.services import auth_sessions
from app.core import security

PASSWORD = 'Synthetic-Session-Test-Password-Only'


@pytest.fixture
def site(monkeypatch):
    monkeypatch.setattr(settings, 'jwt_access_token_expire_minutes', 480)
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        role = Role(name='Session Test Administrator', is_active=True)
        role.set_permissions(['*'])
        user = User(user_code='SESSION-TEST', username='session.test', full_name='Session Test User', password_hash=hash_password(PASSWORD), status='Active', role=role)
        db.add(user); db.commit(); user_id = user.id
    app = FastAPI(); app.include_router(auth.router)
    def database():
        with Session(engine, expire_on_commit=False) as db: yield db
    app.dependency_overrides[get_db] = database
    clock = [datetime.now(timezone.utc).replace(tzinfo=None)]
    monkeypatch.setattr(auth, 'utc_now', lambda: clock[0])
    monkeypatch.setattr(auth_sessions, 'utc_now', lambda: clock[0])
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine, client=client, user_id=user_id, clock=clock)
    engine.dispose()


def login(site, **fields):
    return site.client.post('/api/v1/auth/login', json={'username': 'session.test', 'password': PASSWORD, **fields})


def sign_in(site):
    result = login(site)
    assert result.status_code == 200, result.text
    return {'Authorization': f"Bearer {result.json()['access_token']}"}


def status(site, headers):
    return site.client.get('/api/v1/auth/session', headers=headers)


def claims(headers):
    return jwt.decode(headers['Authorization'].split(' ', 1)[1], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def test_login_has_a_fifteen_minute_lease_and_eight_hour_token(site):
    headers = sign_in(site)
    response = status(site, headers)
    assert response.headers['cache-control'] == 'no-store'
    value = response.json()
    assert value['idle_timeout_seconds'] == 900
    assert value['warning_seconds'] == 60
    assert value['idle_expires_at'] - value['server_time'] == pytest.approx(900, abs=1)
    assert claims(headers)['exp'] - claims(headers)['iat'] == 28800
    assert value['absolute_expires_at'] - value['server_time'] <= 28800


def test_background_requests_do_not_renew_and_expired_sessions_cannot_be_revived(site):
    headers = sign_in(site)
    original = status(site, headers).json()['idle_expires_at']
    for minutes in [1, 5, 10, 14]:
        site.clock[0] += timedelta(minutes=minutes - (0 if minutes == 1 else previous))
        previous = minutes
        assert site.client.get('/api/v1/auth/me', headers=headers).status_code == 200
        assert status(site, headers).json()['idle_expires_at'] == original
    site.clock[0] += timedelta(minutes=1)
    assert status(site, headers).status_code == 401
    assert site.client.post('/api/v1/auth/session/activity', headers=headers).status_code == 401
    fresh = sign_in(site)
    assert status(site, fresh).status_code == 200
    assert status(site, headers).status_code == 401


def test_actual_activity_renews_the_idle_deadline(site):
    headers = sign_in(site)
    before = status(site, headers).json()['idle_expires_at']
    site.clock[0] += timedelta(minutes=10)
    response = site.client.post('/api/v1/auth/session/activity', headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['idle_expires_at'] == pytest.approx(before + 600, abs=1)
    assert response.json()['absolute_expires_at'] == claims(headers)['exp']
    site.clock[0] += timedelta(minutes=14)
    assert status(site, headers).status_code == 200
    site.clock[0] += timedelta(minutes=1)
    assert status(site, headers).status_code == 401


def test_continuous_activity_cannot_extend_absolute_expiry(site):
    headers = sign_in(site)
    absolute = claims(headers)['exp']
    for _ in range(34):
        site.clock[0] += timedelta(minutes=14)
        response = site.client.post('/api/v1/auth/session/activity', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['idle_expires_at'] <= absolute
    site.clock[0] = datetime.fromtimestamp(absolute, timezone.utc).replace(tzinfo=None)
    assert status(site, headers).status_code == 401
    assert site.client.post('/api/v1/auth/session/activity', headers=headers).status_code == 401


def test_a_longer_configured_token_is_capped_at_eight_hours(site, monkeypatch):
    monkeypatch.setattr(settings, 'jwt_access_token_expire_minutes', 1440)
    result = login(site)
    assert result.status_code == 200
    assert result.json()['expires_in'] == 28800


@pytest.mark.parametrize('minutes', [5, 30])
def test_existing_shorter_expiry_is_preserved(site, monkeypatch, minutes):
    monkeypatch.setattr(settings, 'jwt_access_token_expire_minutes', minutes)
    assert login(site).json()['expires_in'] == minutes * 60
    with Session(site.engine) as db:
        user = db.get(User, site.user_id)
        # Even without another status request, a short token must not leave
        # its account reserved after the absolute deadline has elapsed.
        assert user.active_session_expires_at <= site.clock[0] + timedelta(minutes=min(minutes, 15))
    site.clock[0] += timedelta(minutes=minutes)
    assert login(site).status_code == 200


def test_logout_revokes_the_session_and_releases_account(site):
    headers = sign_in(site)
    assert login(site).status_code == 409
    assert site.client.post('/api/v1/auth/logout', headers=headers).status_code == 200
    assert status(site, headers).status_code == 401
    assert site.client.post('/api/v1/auth/session/activity', headers=headers).status_code == 401
    assert login(site).status_code == 200


def test_stale_logout_cannot_revoke_a_newer_login(site):
    headers = sign_in(site)
    with Session(site.engine) as db:
        old = db.get(User, site.user_id)
        # Simulate the old request passing its dependency, followed by expiry and a new login.
        db.expunge(old)
    site.clock[0] += timedelta(minutes=16)
    fresh = sign_in(site)
    with Session(site.engine) as db:
        auth.logout(db=db, current_user=old)
    assert status(site, fresh).status_code == 200
    assert status(site, headers).status_code == 401


def test_legacy_persistent_tokens_are_rejected_and_long_old_leases_are_reclaimable(site):
    headers = sign_in(site)
    old = claims(headers); old.pop('sp'); old.pop('iat')
    old_header = {'Authorization': 'Bearer ' + jwt.encode(old, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)}
    with Session(site.engine) as db:
        user = db.get(User, site.user_id)
        user.active_session_expires_at = site.clock[0] + timedelta(hours=8)
        db.commit()
    assert status(site, old_header).status_code == 401
    assert login(site).status_code == 200
    assert status(site, old_header).status_code == 401


@pytest.mark.parametrize('age,expected', [(5, 200), (16, 401)])
def test_first_use_of_trusted_tokens_is_anchored_to_issuance_not_polling(site, age, expected):
    token, _ = create_access_token(site.user_id)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    payload['iat'] -= age * 60
    payload['exp'] -= age * 60
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    response = status(site, {'Authorization': f'Bearer {token}'})
    assert response.status_code == expected
    if expected == 200:
        assert response.json()['idle_expires_at'] == pytest.approx(payload['iat'] + 900, abs=1)


def test_two_factor_sign_in_still_claims_a_temporary_session(site):
    secret = pyotp.random_base32()
    with Session(site.engine) as db:
        user = db.get(User, site.user_id); user.two_factor_enabled = True; user.two_factor_secret = secret; db.commit()
    challenge = login(site)
    assert challenge.status_code == 200 and challenge.json()['requires_two_factor']
    with Session(site.engine) as db: assert db.get(User, site.user_id).active_session_expires_at is None
    result = site.client.post('/api/v1/auth/login/2fa', json={'challenge_token': challenge.json()['challenge_token'], 'otp_code': pyotp.TOTP(secret).now()})
    assert result.status_code == 200, result.text
    value = status(site, {'Authorization': f"Bearer {result.json()['access_token']}"}).json()
    assert value['idle_expires_at'] - value['server_time'] == pytest.approx(900, abs=1)


def test_anonymous_activity_cannot_start_a_session(site):
    assert site.client.post('/api/v1/auth/session/activity').status_code in {401, 403}
    with Session(site.engine) as db: assert db.get(User, site.user_id).active_session_expires_at is None


def test_trusted_tokens_cannot_inherit_a_long_legacy_idle_lease(site):
    with Session(site.engine) as db:
        user = db.get(User, site.user_id)
        user.active_session_auth_version = 0
        user.active_session_expires_at = site.clock[0] + timedelta(hours=8)
        db.commit()
    token, _ = create_access_token(site.user_id)
    response = status(site, {'Authorization': f'Bearer {token}'})
    assert response.status_code == 200, response.text
    assert response.json()['idle_expires_at'] - response.json()['server_time'] <= 900


def test_stale_activity_cannot_modify_a_new_login(site):
    headers = sign_in(site)
    with Session(site.engine) as db:
        old = auth.get_current_user(credentials=auth.HTTPAuthorizationCredentials(scheme='Bearer', credentials=headers['Authorization'].split(' ', 1)[1]), db=db)
        db.expunge(old)
    site.clock[0] += timedelta(minutes=16)
    fresh = sign_in(site)
    before = status(site, fresh).json()['idle_expires_at']
    with Session(site.engine) as db:
        with pytest.raises(auth.HTTPException) as error:
            auth_sessions.renew_session(db, old)
        assert error.value.status_code == 401
    assert status(site, fresh).json()['idle_expires_at'] == before
