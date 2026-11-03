"""Local credentials authorize exactly one eligible reversal without changing sessions."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import jwt,pyotp,pytest
from sqlalchemy import event,func,select
from sqlalchemy.orm import Session
from test_task_void_policy import work,approve
from test_resource_monitoring import farm
from app.core.config import settings
from app.core.security import create_access_token,hash_password
from app.models import AuditLog,FarmActivity,InventoryItem,InventoryStockRecord,Role,User
from app.models.void_operation import VoidOperation
from app.routers import void_authorizations,resource_usages,production_sales

PASSWORD='Synthetic-Owner-Password-Only-For-Tests'

@pytest.fixture
def approved(work):
    work.client.app.include_router(void_authorizations.router)
    work.client.app.include_router(resource_usages.router)
    work.client.app.include_router(production_sales.router)
    with Session(work.engine) as db:
        owner=db.get(User,work.users['manager']);owner.password_hash=hash_password(PASSWORD)
        role=Role(name='Operations Reviewer',is_active=True);role.set_permissions(['workforce:review','workforce:manage','crops:update','production_sales:update'])
        operator=User(user_code='VOID-OPS',username='void.ops',full_name='Operations Reviewer',password_hash=hash_password('Synthetic-Ops-Password'),status='Active',role=role)
        db.add(operator);db.flush();work.users['operator']=operator.id
        work.headers['operator']={'Authorization':f'Bearer {create_access_token(operator.id)[0]}'};db.commit()
    approve(work)
    return work


def preview(approved,role='worker',action='task',record_id=None):
    response=approved.client.get('/api/v1/void-authorizations/preview',params={'action':action,'record_id':record_id or approved.tasks['Crop']},headers=approved.headers[role])
    assert response.status_code==200,response.text
    return response.json()


def payload(approved,**changes):
    return {'preview_token':preview(approved)['preview_token'],'reason':'Wrong performed-work entry',
            'owner_username':'monitoring.manager','owner_password':PASSWORD,**changes}


def execute(approved,data,role='worker'):
    return approved.client.post('/api/v1/void-authorizations',json=data,headers=approved.headers[role])


def stock(approved):
    with Session(approved.engine) as db:return float(db.get(InventoryItem,approved.item_id).quantity)


def test_employee_and_operational_reviewer_cannot_directly_void(approved):
    for role in ('worker','operator'):
        assert approved.client.post(approved.task_url+'/void',json={'reason':'Wrong entry'},headers=approved.headers[role]).status_code==403
    assert stock(approved)==8


def test_authorized_void_is_atomic_idempotent_and_keeps_sessions(approved):
    with Session(approved.engine) as db:
        before={u.id:(u.auth_version,u.active_session_auth_version,u.last_login) for u in db.scalars(select(User)).all()}
    data=payload(approved)
    result=execute(approved,data);assert result.status_code==200,result.text
    retry=execute(approved,data);assert retry.status_code==200 and retry.json()['replayed']
    assert stock(approved)==10
    assert execute(approved,{**data,'reason':'Another reason'}).status_code==409
    with Session(approved.engine) as db:
        saved=db.scalar(select(VoidOperation));assert saved.requester_user_id==approved.users['worker'] and saved.authorizer_user_id==approved.users['manager']
        assert db.scalar(select(func.count()).select_from(VoidOperation))==1
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord).where(InventoryStockRecord.adjustment_type=='Usage Reversal'))==1
        after={u.id:(u.auth_version,u.active_session_auth_version,u.last_login) for u in db.scalars(select(User)).all()}
        assert before==after
        audit=db.scalar(select(AuditLog).where(AuditLog.action=='Owner/Admin authorized void'))
        assert 'Monitoring worker' in audit.details and 'Monitoring manager' in audit.details and PASSWORD not in audit.details
    assert approved.client.get('/api/v1/workforce/my-tasks',headers=approved.headers['worker']).status_code==200
    assert approved.client.get('/api/v1/users',headers=approved.headers['worker']).status_code in (403,404)


@pytest.mark.parametrize('change',[{'owner_password':'Wrong password'},{'owner_username':'void.ops','owner_password':'Synthetic-Ops-Password'},{'owner_username':'missing'},{'owner_username':None,'owner_password':None}])
def test_wrong_or_non_admin_credentials_never_reverse_work(approved,change):
    response=execute(approved,payload(approved,**change));assert response.status_code==403,response.text
    assert stock(approved)==8
    with Session(approved.engine) as db:assert db.scalar(select(func.count()).select_from(VoidOperation))==0


def test_authorizer_must_be_active_and_2fa_is_enforced(approved):
    secret=pyotp.random_base32()
    with Session(approved.engine) as db:
        owner=db.get(User,approved.users['manager']);owner.two_factor_enabled=True;owner.two_factor_secret=secret;db.commit()
    data=payload(approved)
    assert execute(approved,data).status_code==403
    assert execute(approved,{**data,'otp_code':'000000'}).status_code==403
    response=execute(approved,{**data,'otp_code':pyotp.TOTP(secret).now()})
    assert response.status_code==200,response.text


def test_disabled_owner_cannot_authorize(approved):
    data=payload(approved)
    with Session(approved.engine) as db:db.get(User,approved.users['manager']).status='Disabled';db.commit()
    assert execute(approved,data).status_code==403 and stock(approved)==8


def test_preview_cannot_be_used_by_another_user_or_as_a_login_token(approved):
    data=payload(approved)
    assert execute(approved,data,role='other').status_code==409
    foreign=approved.client.get('/api/v1/void-authorizations/preview',params={'action':'task','record_id':approved.tasks['Crop']},headers=approved.headers['other'])
    assert foreign.status_code==403
    response=approved.client.get('/api/v1/workforce/my-tasks',headers={'Authorization':'Bearer '+data['preview_token']})
    assert response.status_code==401


@pytest.mark.parametrize('kind',['expired','wrong-purpose','changed-record'])
def test_expired_or_stale_previews_are_refused(approved,kind):
    data=payload(approved)
    if kind=='changed-record':
        with Session(approved.engine) as db:db.get(FarmActivity,approved.tasks['Crop']).instructions='Changed after preview';db.commit()
    else:
        claims=jwt.decode(data['preview_token'],settings.jwt_secret_key,algorithms=[settings.jwt_algorithm])
        if kind=='expired':claims['exp']=datetime.now(timezone.utc)-timedelta(seconds=1)
        else:claims['purpose']='access'
        data['preview_token']=jwt.encode(claims,settings.jwt_secret_key,algorithm=settings.jwt_algorithm)
    assert execute(approved,data).status_code==409 and stock(approved)==8


def test_only_one_of_two_previews_can_restore_stock(approved):
    first=payload(approved);second=payload(approved)
    assert execute(approved,first).status_code==200
    assert execute(approved,second).status_code==409 and stock(approved)==10


def test_protected_monitoring_and_task_linked_usage_cannot_bypass_task_rules(approved):
    response=approved.client.get('/api/v1/void-authorizations/preview',params={'action':'task','record_id':approved.tasks['Livestock']},headers=approved.headers['manager'])
    assert response.status_code==409
    from app.models import ResourceUsage
    with Session(approved.engine) as db:usage=db.scalar(select(ResourceUsage))
    response=approved.client.get('/api/v1/void-authorizations/preview',params={'action':'resource_usage','record_id':usage.id},headers=approved.headers['manager'])
    assert response.status_code==409
    assert approved.client.delete(f'/api/v1/resource-usages/{usage.id}',params={'reason':'Wrong usage'},headers=approved.headers['manager']).status_code==409
    assert stock(approved)==8


def test_failed_operation_rolls_back_stock_audit_and_authorization(approved):
    data=payload(approved)
    def fail_operation(session,context,instances):
        if any(isinstance(row,VoidOperation) for row in session.new):raise RuntimeError('Forced persistence failure')
    event.listen(Session,'before_flush',fail_operation)
    try:
        with pytest.raises(RuntimeError):execute(approved,data)
    finally:event.remove(Session,'before_flush',fail_operation)
    assert stock(approved)==8
    with Session(approved.engine) as db:
        assert db.get(FarmActivity,approved.tasks['Crop']).status=='Completed'
        assert db.scalar(select(func.count()).select_from(VoidOperation))==0
    assert execute(approved,data).status_code==200 and stock(approved)==10


def test_failed_attempts_are_limited_and_validation_does_not_echo_password(approved):
    data=payload(approved,owner_password='Wrong password')
    for _ in range(5):assert execute(approved,data).status_code==403
    assert execute(approved,data).status_code==429 and stock(approved)==8
    response=execute(approved,{**data,'owner_password':'SECRET-SENTINEL'*20})
    assert response.status_code==422 and 'SECRET-SENTINEL' not in response.text


def test_admin_can_use_the_same_dialog_without_entering_another_password(approved):
    data={'preview_token':preview(approved,role='manager')['preview_token'],'reason':'Owner confirmed wrong work'}
    response=execute(approved,data,role='manager');assert response.status_code==200,response.text
    assert stock(approved)==10


@pytest.mark.parametrize('action',['resource_usage','sale','processing'])
def test_other_reversals_need_owner_authorization_and_restore_once(approved,action):
    from app.models import Livestock
    if action=='resource_usage':
        created=approved.client.post('/api/v1/resource-usages',json={'module':'Crop','target_id':approved.ids['Crop'],'inventory_item_id':approved.item_id,'usage_type':'Fertilizer','quantity':1,'usage_date':str(approved.today)},headers=approved.headers['manager'])
        path='/api/v1/resource-usages'
    elif action=='sale':
        with Session(approved.engine) as db:
            product=InventoryItem(item_code='VOID-PRODUCT',name='Synthetic Sale Product',category='Processed Product',quantity=20,unit='pcs',supplier='Test',date_acquired=approved.today,location='Test',is_saleable=True)
            db.add(product);db.flush();approved.product_id=product.id;db.commit()
        created=approved.client.post('/api/v1/production-sales/sales',json={'sale_date':str(approved.today),'items':[{'item_kind':'Inventory','inventory_item_id':approved.product_id,'quantity':2,'unit_price':10}],'payment_status':'Paid','amount_paid':20},headers=approved.headers['manager'])
        path='/api/v1/production-sales/sales'
    else:
        with Session(approved.engine) as db:
            animal=db.get(Livestock,approved.ids['Livestock']);animal.production_purpose='Meat';animal.male_quantity=10;animal.female_quantity=0;animal.unknown_sex_quantity=0;db.commit()
        created=approved.client.post('/api/v1/production-sales/processing',json={'livestock_id':approved.ids['Livestock'],'processing_date':str(approved.today),'animals_processed':1,'male_quantity':1,'live_weight_kg':10,'meat_output_kg':5},headers=approved.headers['manager'])
        path='/api/v1/production-sales/processing'
    assert created.status_code==201,created.text
    record_id=created.json()['id']
    denied=approved.client.delete(f'{path}/{record_id}',params={'reason':'Wrong entry'},headers=approved.headers['operator']) if action=='resource_usage' else approved.client.post(f'{path}/{record_id}/void',json={'reason':'Wrong entry'},headers=approved.headers['operator'])
    assert denied.status_code==403
    data={'preview_token':preview(approved,role='operator',action=action,record_id=record_id)['preview_token'],'reason':'Owner authorized reversal','owner_username':'monitoring.manager','owner_password':PASSWORD}
    response=execute(approved,data,role='operator');assert response.status_code==200,response.text
    assert execute(approved,data,role='operator').status_code==200
    with Session(approved.engine) as db:
        if action=='resource_usage':assert float(db.get(InventoryItem,approved.item_id).quantity)==8
        elif action=='sale':assert float(db.get(InventoryItem,approved.product_id).quantity)==20
        else:assert db.get(Livestock,approved.ids['Livestock']).quantity==10
