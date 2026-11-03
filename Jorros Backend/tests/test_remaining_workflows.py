"""Regression coverage for remaining resource, chronology and farm-clock defects."""
from datetime import datetime,timedelta,time,timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func,select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from app.core.farm_time import farm_today
from app.models import (FarmCreationCommand,InventoryItem,InventoryStockRecord,Livestock,
                        LivestockVaccinationRecord,ResourceUsage,User,FarmActivity,LivestockTransaction)
from app.routers import resource_usages,production_sales
from app.routers.workforce_handlers import _sync_vaccination_history_from_task
from app.services.resource_usage_service import update_usage,void_usage


def item(farm,category='Fertilizer'):
    with Session(farm.engine) as db:
        row=InventoryItem(item_code='REST-'+category,name='Synthetic Test '+category,category=category,
                          quantity=100,unit='kg',supplier='Test',date_acquired=farm.today-timedelta(days=30),location='Test')
        db.add(row);db.commit();return row.id


@pytest.fixture
def usage(farm):
    farm.client.app.include_router(resource_usages.router)
    farm.item_id=item(farm)
    farm.payload={'module':'Crop','target_id':farm.ids['Crop'],'inventory_item_id':farm.item_id,
                  'usage_type':'Fertilizer','quantity':2,'usage_date':str(farm.today)}
    first=farm.client.post('/api/v1/resource-usages',json=farm.payload,
                          headers={**farm.headers['manager'],'Idempotency-Key':'one-manual-use'})
    assert first.status_code==201,first.text
    farm.usage_id=first.json()['id'];return farm


def quantity(farm):
    with Session(farm.engine) as db:return float(db.get(InventoryItem,farm.item_id).quantity)


def test_manual_usage_retries_and_conflicts_do_not_deduct_again(usage):
    headers={**usage.headers['manager'],'Idempotency-Key':'one-manual-use'}
    again=usage.client.post('/api/v1/resource-usages',json=usage.payload,headers=headers)
    assert again.status_code==201 and again.json()['id']==usage.usage_id
    assert quantity(usage)==98
    assert usage.client.post('/api/v1/resource-usages',json={**usage.payload,'quantity':3},headers=headers).status_code==409
    assert usage.client.post('/api/v1/resource-usages',json=usage.payload,
                             headers={**usage.headers['worker'],'Idempotency-Key':'one-manual-use'}).status_code==403
    with Session(usage.engine) as db:
        assert db.scalar(select(func.count()).select_from(ResourceUsage))==1
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord))==1
        assert db.scalar(select(func.count()).select_from(FarmCreationCommand))==1


def test_interleaved_voids_cannot_restore_one_usage_twice(usage):
    with Session(usage.engine,expire_on_commit=False) as first,Session(usage.engine,expire_on_commit=False) as second:
        a=first.get(ResourceUsage,usage.usage_id);b=second.get(ResourceUsage,usage.usage_id)
        actor1=first.get(User,usage.users['manager']);actor2=second.get(User,usage.users['manager'])
        void_usage(first,usage=a,reason='Wrong entry',current_user=actor1);first.commit()
        with pytest.raises(HTTPException) as error:
            void_usage(second,usage=b,reason='Repeated entry',current_user=actor2)
        assert error.value.status_code==400
        second.rollback()
    assert quantity(usage)==100
    with Session(usage.engine) as db:
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord).where(
            InventoryStockRecord.adjustment_type=='Usage Restored'))==1


def test_stale_corrections_use_the_latest_usage_and_stock(usage):
    with Session(usage.engine,expire_on_commit=False) as first,Session(usage.engine,expire_on_commit=False) as second:
        a=first.get(ResourceUsage,usage.usage_id);b=second.get(ResourceUsage,usage.usage_id)
        # Cache the old stock too, before another transaction changes it.
        second.get(InventoryItem,usage.item_id)
        actor1=first.get(User,usage.users['manager']);actor2=second.get(User,usage.users['manager'])
        update_usage(first,usage=a,changes={'quantity':5},current_user=actor1);first.commit()
        update_usage(second,usage=b,changes={'quantity':3},current_user=actor2);second.commit()
    assert quantity(usage)==97
    with Session(usage.engine) as db:assert float(db.get(ResourceUsage,usage.usage_id).quantity)==3


def test_usage_creation_failure_rolls_back_stock_and_retry_marker(farm):
    farm.client.app.include_router(resource_usages.router);farm.item_id=item(farm)
    payload={'module':'Crop','target_id':farm.ids['Crop'],'inventory_item_id':farm.item_id,
             'usage_type':'Fertilizer','quantity':2,'usage_date':str(farm.today)}
    headers={**farm.headers['manager'],'Idempotency-Key':'failed-manual-use'}
    with patch('app.routers.resource_usages.record_creation_command',side_effect=RuntimeError('Forced failure')):
        with pytest.raises(RuntimeError):farm.client.post('/api/v1/resource-usages',json=payload,headers=headers)
    assert quantity(farm)==100
    with Session(farm.engine) as db:assert db.scalar(select(func.count()).select_from(FarmCreationCommand))==0
    assert farm.client.post('/api/v1/resource-usages',json=payload,headers=headers).status_code==201
    assert quantity(farm)==98


def test_correction_failure_rolls_back_and_blank_void_reason_is_rejected(usage):
    with patch('app.services.resource_usage_service._add_audit',side_effect=RuntimeError('Forced audit failure')):
        with pytest.raises(RuntimeError):
            usage.client.put(f'/api/v1/resource-usages/{usage.usage_id}',json={'quantity':5},headers=usage.headers['manager'])
    assert quantity(usage)==98
    response=usage.client.delete(f'/api/v1/resource-usages/{usage.usage_id}',params={'reason':'   '},headers=usage.headers['manager'])
    assert response.status_code==400 and quantity(usage)==98


def vaccination(farm,*,days_ago=0,next_days=60,key='newest-vax'):
    return farm.client.post(f'/api/v1/livestock/{farm.ids["Livestock"]}/vaccination-records',json={
        'vaccine':'Synthetic Test Vaccine','date_administered':str(farm.today-timedelta(days=days_ago)),
        'next_due':str(farm.today+timedelta(days=next_days)),'status':'Up to Date',
        'inventory_item_id':farm.item_id,'quantity_used':2},headers={**farm.headers['manager'],'Idempotency-Key':key})


def test_older_vaccinations_preserve_current_summary_and_retries(farm):
    farm.item_id=item(farm,'Vaccine')
    newest=vaccination(farm);assert newest.status_code==201,newest.text
    old=vaccination(farm,days_ago=10,next_days=10,key='historical-vax');assert old.status_code==201,old.text
    retry=vaccination(farm,days_ago=10,next_days=10,key='historical-vax')
    assert retry.json()['id']==old.json()['id'] and quantity(farm)==96
    with Session(farm.engine) as db:
        animal=db.get(Livestock,farm.ids['Livestock'])
        assert animal.last_checkup==farm.today and animal.next_vaccination==farm.today+timedelta(days=60)
        assert db.scalar(select(func.count()).select_from(LivestockVaccinationRecord))==2


def test_approved_old_task_vaccination_cannot_replace_newer_summary(farm):
    farm.item_id=item(farm,'Vaccine');assert vaccination(farm).status_code==201
    with Session(farm.engine) as db:
        task=db.get(FarmActivity,farm.tasks['Livestock'])
        task.activity_date=farm.today-timedelta(days=10);task.planned_usage_type='Vaccine'
        _sync_vaccination_history_from_task(db,task=task,submission=SimpleNamespace(employee_id=farm.employees['worker']),
                                           item=db.get(InventoryItem,farm.item_id),actual_quantity=2,
                                           current_user=db.get(User,farm.users['manager']))
        db.commit()
        animal=db.get(Livestock,farm.ids['Livestock'])
        assert animal.last_checkup==farm.today and animal.next_vaccination==farm.today+timedelta(days=60)
        assert db.scalar(select(func.count()).select_from(LivestockVaccinationRecord))==2


@pytest.mark.parametrize('operation',['production','reproduction'])
@pytest.mark.parametrize('future',[False,True])
def test_production_dates_follow_farm_day_not_server_day(farm,operation,future):
    farm.client.app.include_router(production_sales.router)
    server_now=datetime.combine(farm.today+(timedelta(days=1) if future else -timedelta(days=1)),time(18))
    if not future:assert farm_today(server_now.replace(tzinfo=timezone.utc))==farm.today
    record_day=farm.today+timedelta(days=int(future))
    if operation=='production':
        with Session(farm.engine) as db:
            animal=db.get(Livestock,farm.ids['Livestock']);animal.animal_type='Chicken'
            animal.production_purpose='Egg Production';animal.female_quantity=10;db.commit()
        payload={'livestock_id':farm.ids['Livestock'],'output_type':'Eggs','record_date':str(record_day),
                 'source_active_quantity':10,'gross_quantity':5,'quantity':5,'unit':'pcs'}
    else:payload={'livestock_id':farm.ids['Livestock'],'record_type':'Birth','event_date':str(record_day)}
    class ServerClock(datetime):
        @classmethod
        def now(cls,tz=None):return server_now if tz is None else server_now.replace(tzinfo=timezone.utc).astimezone(tz)
    with patch('app.services.production_sales_service.datetime',ServerClock):
        response=farm.client.post('/api/v1/production-sales/'+operation,json=payload,headers=farm.headers['manager'])
    assert response.status_code==(400 if future else 201),response.text


@pytest.mark.parametrize('operation',['processing','sale'])
def test_stock_and_animal_reversals_use_the_farm_date(farm,operation):
    farm.client.app.include_router(production_sales.router)
    with Session(farm.engine) as db:
        animal=db.get(Livestock,farm.ids['Livestock'])
        animal.production_purpose='Meat';animal.male_quantity=10
        animal.female_quantity=0;animal.unknown_sex_quantity=0
        db.commit()
    if operation=='processing':
        created=farm.client.post('/api/v1/production-sales/processing',headers=farm.headers['manager'],json={
            'livestock_id':farm.ids['Livestock'],'processing_date':str(farm.today),'animals_processed':1,
            'male_quantity':1,'meat_output_kg':5,'live_weight_kg':10})
        path='/api/v1/production-sales/processing'
    else:
        farm.item_id=item(farm,'Processed Product')
        with Session(farm.engine) as db:
            db.get(InventoryItem,farm.item_id).is_saleable=True;db.commit()
        created=farm.client.post('/api/v1/production-sales/sales',headers=farm.headers['manager'],json={
            'sale_date':str(farm.today),'items':[
                {'item_kind':'Live Animal','livestock_id':farm.ids['Livestock'],'quantity':1,'male_quantity':1,'unit_price':100},
                {'item_kind':'Inventory','inventory_item_id':farm.item_id,'quantity':2,'unit_price':10}],
            'payment_status':'Paid','amount_paid':120})
        path='/api/v1/production-sales/sales'
    assert created.status_code==201,created.text
    class ServerClock(datetime):
        @classmethod
        def now(cls,tz=None):
            value=datetime.combine(farm.today-timedelta(days=1),time(18))
            return value if tz is None else value.replace(tzinfo=timezone.utc).astimezone(tz)
    with patch('app.services.production_sales_service.datetime',ServerClock):
        response=farm.client.post(f'{path}/{created.json()["id"]}/void',json={'reason':'Synthetic test reversal'},headers=farm.headers['manager'])
    assert response.status_code==200,response.text
    with Session(farm.engine) as db:
        movement=db.scalar(select(LivestockTransaction).where(LivestockTransaction.transaction_type==('Processing Void' if operation=='processing' else 'Sale Void')))
        assert movement.event_date==farm.today
        assert db.get(Livestock,farm.ids['Livestock']).quantity==10
        if operation=='sale':
            restored=db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.adjustment_type=='Returned'))
            assert restored.adjustment_date==farm.today
            assert float(db.get(InventoryItem,farm.item_id).quantity)==100
