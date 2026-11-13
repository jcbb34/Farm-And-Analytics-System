"""Exercise real HTTP contracts for stock corrections, history pages and supply choices."""
from datetime import timedelta
import hashlib
import json
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_record_edit_versions import versioned
from app.models import InventoryItem, InventoryStockRecord, AuditLog, User
from app.routers import inventory

@pytest.fixture(autouse=True)
def no_farm_task_sync(monkeypatch):
    monkeypatch.setattr(inventory, '_run_stock_adjustment_task_sync', lambda: None)

def adjustment(site, *, kind='Set Exact Quantity', quantity=80, version=None, key=None):
    payload=dict(adjustment_type=kind,quantity=quantity,adjustment_date=str(site.today),reason='Verified physical stock count')
    if version is not None:payload['expected_version']=version
    headers=site.headers('ADMIN')
    if key:headers={**headers,'Idempotency-Key':key}
    return site.client.post(f"/api/v1/inventory/{site.record_ids['inventory']}/stock-adjustments",json=payload,headers=headers)

def metadata(site):
    return site.get(f"/api/v1/inventory/{site.record_ids['inventory']}",include_history=False)

def test_exact_count_cannot_overwrite_a_newer_stock_transaction(versioned):
    site=versioned; initial=metadata(site)
    restock=adjustment(site,kind='Restock',quantity=25)
    assert restock.status_code==201,restock.text
    assert restock.json()['inventory_edit_version']>initial['edit_version']
    assert restock.json()['inventory_previous_edit_version']==initial['edit_version']
    with Session(site.engine) as db:
        movements=db.scalar(select(func.count()).select_from(InventoryStockRecord))
        audits=db.scalar(select(func.count()).select_from(AuditLog))
    stale=adjustment(site,version=initial['edit_version'])
    assert stale.status_code==409 and stale.headers['x-record-conflict']=='RECORD_CONFLICT'
    assert metadata(site)['quantity']==125
    with Session(site.engine) as db:
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord))==movements
        assert db.scalar(select(func.count()).select_from(AuditLog))==audits
    saved=adjustment(site,version=metadata(site)['edit_version'])
    assert saved.status_code==201,saved.text
    assert saved.json()['previous_quantity']==125 and saved.json()['new_quantity']==80
    assert metadata(site)['quantity']==80

def test_exact_count_requires_valid_version_but_relative_usage_stays_relative(versioned):
    site=versioned
    missing=adjustment(site)
    assert missing.status_code==428 and missing.headers['x-record-conflict']=='RECORD_VERSION_REQUIRED'
    for bad in [0,-2]:assert adjustment(site,version=bad).status_code==422
    assert adjustment(site,kind='Stock Usage',quantity=5).status_code==201
    assert adjustment(site,kind='Restock',quantity=10).status_code==201
    assert metadata(site)['quantity']==105

def test_successful_exact_retry_is_not_applied_again_after_later_stock_changes(versioned):
    site=versioned; version=metadata(site)['edit_version']
    saved=adjustment(site,version=version,key='exact-count-retry')
    assert saved.status_code==201
    assert adjustment(site,kind='Restock',quantity=20).status_code==201
    replay=adjustment(site,version=version,key='exact-count-retry')
    assert replay.status_code==201 and replay.json()['id']==saved.json()['id']
    assert replay.json()['inventory_edit_version'] is None
    assert metadata(site)['quantity']==100
    assert adjustment(site,version=version,key='exact-count-retry',quantity=70).status_code==409

def test_retry_from_before_update_keeps_original_fingerprint(versioned):
    site=versioned; identifier=site.record_ids['inventory']
    payload=dict(adjustment_type='Restock',quantity=5.0,adjustment_date=str(site.today),reason='Verified physical stock count',reference=None,supplier=None)
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    with Session(site.engine) as db:
        record=InventoryStockRecord(inventory_item_id=identifier,adjustment_type='Restock',quantity=5,previous_quantity=95,new_quantity=100,adjustment_date=site.today,reason=payload['reason'],idempotency_key='legacy-retry',request_hash=fingerprint,recorded_by_user_id=site.user_ids['ADMIN'])
        db.add(record);db.commit();record_id=record.id
    response=adjustment(site,kind='Restock',quantity=5,key='legacy-retry')
    assert response.status_code==201 and response.json()['id']==record_id,response.text
    assert metadata(site)['quantity']==100

def add_history(site, count=63):
    with Session(site.engine) as db:
        db.add_all([InventoryStockRecord(inventory_item_id=site.record_ids['inventory'],adjustment_type='Restock',quantity=1,previous_quantity=i,new_quantity=i+1,adjustment_date=site.today,reason=f'Historical movement {i}') for i in range(count)])
        db.commit()

def test_metadata_read_does_not_load_history_and_legacy_detail_is_preserved(versioned):
    site=versioned;add_history(site)
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(site.engine,'before_cursor_execute',capture)
    try:light=metadata(site)
    finally:event.remove(site.engine,'before_cursor_execute',capture)
    assert not light['stock_history_included'] and light['stock_history']==[]
    assert not any('FROM inventory_stock_records' in sql for sql in statements),statements
    legacy=site.get(f"/api/v1/inventory/{site.record_ids['inventory']}")
    assert legacy['stock_history_included'] and len(legacy['stock_history'])==63

def test_history_pages_pin_snapshot_when_new_movements_arrive(versioned):
    site=versioned;add_history(site)
    uri=f"/api/v1/inventory/{site.record_ids['inventory']}/stock-history"
    first=site.get(uri)
    assert first['total']==63 and len(first['items'])==25
    assert adjustment(site,kind='Restock',quantity=10).status_code==201
    second=site.get(uri,offset=25,snapshot_id=first['snapshot_id'])
    third=site.get(uri,offset=50,snapshot_id=first['snapshot_id'])
    rows=first['items']+second['items']+third['items']
    assert len(rows)==63 and len({row['id'] for row in rows})==63
    assert [row['id'] for row in rows]==sorted((row['id'] for row in rows),reverse=True)
    assert second['total']==third['total']==63
    assert site.get(uri)['total']==64
    assert site.get(uri,offset=500,snapshot_id=first['snapshot_id'])['items']==[]

def test_history_permissions_missing_items_and_limits(versioned):
    site=versioned;uri=f"/api/v1/inventory/{site.record_ids['inventory']}/stock-history"
    assert site.client.get(uri).status_code==401
    assert site.client.get(uri,headers=site.headers('WORKER1')).status_code==403
    for query in [{'limit':101},{'offset':-1},{'snapshot_id':-1}]:
        assert site.client.get(uri,headers=site.headers('ADMIN'),params=query).status_code==422
    assert site.client.get('/api/v1/inventory/999999/stock-history',headers=site.headers('ADMIN')).status_code==404

def test_livestock_choices_preserve_rules_and_find_stock_beyond_first_page(versioned):
    site=versioned
    with Session(site.engine) as db:
        rows=[InventoryItem(item_code=f'INV-FEED-PAGE-{i}',name=f'Feed page {i:03}',category='Other',quantity=10,unit='kilograms',reorder_level=0,cost=1,supplier='Test',date_acquired=site.today,location='Store') for i in range(61)]
        db.add_all(rows);db.flush();selected_id=rows[0].id
        for i,(category,name,unit,quantity,expiry,archived) in enumerate([
            ('Feed','Expired feed','kg',10,site.today-timedelta(days=1),False),('Feed','Empty feed','kg',0,None,False),
            ('Feed','Wrong unit feed','bags',10,None,False),('Feed','Archived feed','kg',10,None,True),
            ('Vaccination','Usable vaccine','doses',20,site.today,False),('Farm Supplies','Vaccine name only','doses',20,None,False)]):
            db.add(InventoryItem(item_code=f'INV-INELIGIBLE-{i}',category=category,name=name,unit=unit,quantity=quantity,expiration_date=expiry,is_archived=archived,reorder_level=0,cost=1,supplier='Test',date_acquired=site.today,location='Store'))
        db.commit()
    uri='/api/v1/inventory/choices'
    page=site.get(uri,inventory_use='livestock_feeding',search='Feed page')
    assert page['total']==61 and len(page['items'])==25
    found=site.get(uri,inventory_use='livestock_feeding',search='Feed page 060',selected_id=selected_id)
    assert found['total']==1 and found['items'][0]['name']=='Feed page 060'
    assert found['selected']['id']==selected_id
    vaccine=site.get(uri,inventory_use='livestock_vaccination')
    assert [row['name'] for row in vaccine['items']]==['Usable vaccine']
    feed=site.get(uri,inventory_use='livestock_feeding',limit=100)
    assert not any(row['name'] in ['Expired feed','Empty feed','Wrong unit feed','Archived feed'] for row in feed['items'])
    assert site.client.get(uri,params={'inventory_use':'bad'},headers=site.headers('ADMIN')).status_code==422

def test_livestock_choices_do_not_require_unrelated_activity_access(versioned):
    site=versioned
    with Session(site.engine) as db:
        db.get(User,site.user_ids['MANAGER']).role.set_permissions(['inventory:view','livestock:view'])
        db.commit()
    response=site.client.get('/api/v1/inventory/choices',params={'inventory_use':'livestock_feeding'},headers=site.headers('MANAGER'))
    assert response.status_code==200,response.text
    assert site.client.get('/api/v1/inventory/choices',params={'inventory_use':'livestock_feeding'},headers=site.headers('WORKER1')).status_code==403
