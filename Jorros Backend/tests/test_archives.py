"""Archive policy through real HTTP/auth, including retries and transaction rollback."""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm
from app.models import AuditLog, Crop, Livestock, InventoryItem, FarmReport, FarmActivity, TaskSubmission, User
from app.routers import archives, inventory, reports, users, activities
from app.services.archive_service import change_archive_state


@pytest.fixture
def archive_farm(farm):
    for router in (archives.router, inventory.router, reports.router, users.router, activities.router):
        farm.client.app.include_router(router)
    with Session(farm.engine) as db:
        item = InventoryItem(item_code='ARC-INV', name='Archive feed', category='Livestock Feed', quantity=0,
            unit='kg', reorder_level=0, cost=0, price=0, supplier='Test Supplier', location='Test store', date_acquired=farm.today)
        report = FarmReport(report_code='ARC-REPORT', title='Archive report', category='Crop', report_type='Crop Summary',
            start_date=farm.today, end_date=farm.today, generated_date=farm.today, prepared_by='Test manager',
            status='Final', summary='Saved history', snapshot_json='{"original": true}')
        db.add_all([item, report]); db.flush()
        farm.ids.update(Inventory=item.id, Report=report.id, Employee=farm.employees['other'], User=farm.users['other'], Task=farm.tasks['Crop'])
        db.commit()
    return farm


def post(farm, module, action='archive', role='manager', body=None):
    return farm.client.post(f'/api/v1/archives/{module}/{farm.ids[module]}/{action}',
        json=body if body is not None else ({'reason': 'Closed farm record'} if action == 'archive' else {}), headers=farm.headers[role])


def pending(farm, module):
    with Session(farm.engine) as db:
        task = db.get(FarmActivity, farm.tasks[module]); task.status = 'Pending'; db.commit()


def ledger_count(farm, module, action='Archived'):
    with Session(farm.engine) as db:
        return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.event_type=='archive', AuditLog.module==module, AuditLog.action==action))


@pytest.mark.parametrize('module', ['Crop', 'Livestock', 'Inventory', 'Report', 'Employee', 'User', 'Task'])
def test_employee_cannot_read_or_change_other_modules_archives(archive_farm, module):
    farm = archive_farm
    assert farm.client.get('/api/v1/archives', params={'module':module}, headers=farm.headers['worker']).status_code==403
    assert post(farm,module,role='worker').status_code==403
    assert farm.client.delete(f'/api/v1/archives/{module}/{farm.ids[module]}',headers=farm.headers['worker']).status_code==403
    assert ledger_count(farm,module)==0


@pytest.mark.parametrize('module', ['Crop', 'Livestock', 'Inventory', 'Report'])
@pytest.mark.parametrize('body', [{}, {'reason':'   '}])
def test_archive_reason_is_required_in_backend_without_changing_records(archive_farm,module,body):
    response=post(archive_farm,module,body=body)
    assert response.status_code==422,response.text
    assert ledger_count(archive_farm,module)==0


@pytest.mark.parametrize('module', ['Crop', 'Livestock'])
def test_pending_source_work_and_archive_metadata_commit_once(archive_farm,module):
    farm=archive_farm;pending(farm,module)
    result=post(farm,module,body={'reason':'Cycle completed — reviewed'});assert result.status_code==200,result.text
    assert post(farm,module).status_code==200
    assert ledger_count(farm,module)==1
    with Session(farm.engine) as db:
        task=db.get(FarmActivity,farm.tasks[module]);assert task.is_archived and task.status=='Cancelled'
        model=Crop if module=='Crop' else Livestock;assert db.get(model,farm.ids[module]).is_archived
    data=farm.client.get('/api/v1/archives',params={'module':module},headers=farm.headers['manager']).json()
    row=data['items'][0];assert row['reason']=='Cycle completed — reviewed' and row['archivedBy']=='Monitoring manager'
    assert row['archivedDate'] and data['counts'][module]==1
    assert post(farm,module,'restore').status_code==200
    assert post(farm,module,'restore').status_code==200
    assert ledger_count(farm,module,'Restored')==1
    with Session(farm.engine) as db:
        task=db.get(FarmActivity,farm.tasks[module]);assert task.is_archived and task.status=='Cancelled'


@pytest.mark.parametrize('module', ['Crop','Livestock'])
@pytest.mark.parametrize('status', ['In Progress','Returned','Submitted for Review'])
def test_started_or_unresolved_work_blocks_archiving(archive_farm,module,status):
    farm=archive_farm
    with Session(farm.engine) as db:
        db.get(FarmActivity,farm.tasks[module]).status=status;db.commit()
    result=post(farm,module);assert result.status_code==409,result.text
    assert ledger_count(farm,module)==0
    with Session(farm.engine) as db:assert not db.get(FarmActivity,farm.tasks[module]).is_archived


def test_archive_failure_rolls_back_task_cancellation_and_audit(archive_farm):
    farm=archive_farm;pending(farm,'Crop')
    with Session(farm.engine) as db:
        actor=db.get(User,farm.users['manager'])
        original=db.flush
        def fail_after_flushing(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('Synthetic archive transaction failure')
        with patch.object(db,'flush',side_effect=fail_after_flushing):
            with pytest.raises(RuntimeError):change_archive_state(db,'Crop',farm.ids['Crop'],actor,archive=True,reason='Test rollback')
        db.rollback()
    with Session(farm.engine) as db:
        assert not db.get(Crop,farm.ids['Crop']).is_archived
        assert db.get(FarmActivity,farm.tasks['Crop']).status=='Pending'
    assert ledger_count(farm,'Crop')==0
    assert post(farm,'Crop').status_code==200


def test_remaining_inventory_stock_blocks_both_old_and_new_archive_routes(archive_farm):
    farm=archive_farm
    with Session(farm.engine) as db:db.get(InventoryItem,farm.ids['Inventory']).quantity=2;db.commit()
    assert post(farm,'Inventory').status_code==409
    result=farm.client.post(f'/api/v1/inventory/{farm.ids["Inventory"]}/archive',json={'reason':'Old route'},headers=farm.headers['manager'])
    assert result.status_code==409,result.text
    with Session(farm.engine) as db:
        item=db.get(InventoryItem,farm.ids['Inventory']);assert float(item.quantity)==2 and not item.is_archived


@pytest.mark.parametrize('status', ['Draft','For Review','Approved','Final','Revised','Needs Review','In Progress','Failed'])
def test_restoring_a_report_preserves_original_status_snapshot_and_approval(archive_farm,status):
    farm=archive_farm
    with Session(farm.engine) as db:
        report=db.get(FarmReport,farm.ids['Report']);report.status=status;report.approved_at=datetime(2026,10,1)
        original_lock=report.is_locked;db.commit()
    assert post(farm,'Report').status_code==200
    result=farm.client.post(f'/api/v1/reports/{farm.ids["Report"]}/restore',headers=farm.headers['manager']);assert result.status_code==200,result.text
    with Session(farm.engine) as db:
        report=db.get(FarmReport,farm.ids['Report']);assert report.status==status
        assert report.snapshot_json=='{"original": true}' and report.approved_at==datetime(2026,10,1)
        assert report.is_locked==original_lock


def test_legacy_report_without_saved_status_is_restored_for_review_not_auto_approved(archive_farm):
    farm=archive_farm
    with Session(farm.engine) as db:
        report=db.get(FarmReport,farm.ids['Report']);report.status='Archived';report.archived_from_status=None;db.commit()
    assert post(farm,'Report','restore').status_code==200
    with Session(farm.engine) as db:
        report=db.get(FarmReport,farm.ids['Report'])
        assert report.status=='Needs Review' and report.approved_at is None and report.snapshot_json=='{"original": true}'


def test_legacy_unknown_archive_details_are_not_guessed(archive_farm):
    farm=archive_farm
    with Session(farm.engine) as db:
        crop=db.get(Crop,farm.ids['Crop']);crop.is_archived=True;crop.updated_at=datetime(2026,10,2);db.commit()
    data=farm.client.get('/api/v1/archives',params={'module':'Crop'},headers=farm.headers['manager']).json()
    row=data['items'][0];assert row['archivedDate'] is None and row['archivedBy']=='Not recorded' and row['reason']=='Not recorded'


def test_archive_index_includes_accounts_staff_and_cancelled_work(archive_farm):
    farm=archive_farm
    assert post(farm,'Employee').status_code==200
    assert post(farm,'User').status_code==200
    pending(farm,'Crop');assert post(farm,'Crop').status_code==200
    response=farm.client.get('/api/v1/archives',headers=farm.headers['manager']);assert response.status_code==200,response.text
    data=response.json();assert {'Employee','User','Crop','Task'} <= {row['module'] for row in data['items']}
    assert data['counts']['Task']==1 and data['counts']['Crop']==1
    assert all('password_hash' not in row['details'] and 'two_factor_secret' not in row['details'] for row in data['items'])


def test_index_search_date_pagination_and_focused_navigation(archive_farm):
    farm=archive_farm;pending(farm,'Crop');assert post(farm,'Crop').status_code==200;assert post(farm,'Inventory').status_code==200
    path='/api/v1/archives';headers=farm.headers['manager']
    page=farm.client.get(path,params={'limit':1,'offset':1},headers=headers).json();assert len(page['items'])==1 and page['total']==3
    searched=farm.client.get(path,params={'search':'ARC-INV'},headers=headers).json();assert searched['total']==1
    focused=farm.client.get(path,params={'module':'Crop','focus_id':farm.ids['Crop'],'search':'would hide target','date_from':'2099-01-01','offset':50},headers=headers)
    assert focused.status_code==200 and focused.json()['items'][0]['sourceId']==farm.ids['Crop']
    assert focused.json()['offset']==0
    assert farm.client.get(path,params={'date_from':'2026-10-10','date_to':'2026-09-01'},headers=headers).status_code==422
    assert post(farm,'Crop','restore').status_code==200
    assert farm.client.get(path,params={'module':'Crop','focus_id':farm.ids['Crop']},headers=headers).status_code==409
    assert farm.client.get(path,params={'module':'Crop','focus_id':999999},headers=headers).status_code==404


def test_permanent_deletion_protects_history_and_admin_boundary(archive_farm):
    farm=archive_farm;pending(farm,'Crop');assert post(farm,'Crop').status_code==200
    path=f'/api/v1/crops/{farm.ids["Crop"]}/permanent'
    assert farm.client.delete(path,headers=farm.headers['reviewer']).status_code==403
    assert farm.client.delete(path,headers=farm.headers['manager']).status_code==409
    assert post(farm,'Report').status_code==200
    assert farm.client.delete(f'/api/v1/reports/{farm.ids["Report"]}/permanent',headers=farm.headers['manager']).status_code==409


def test_an_unlinked_zero_stock_archive_can_be_deleted_without_changing_other_records(archive_farm):
    farm=archive_farm;assert post(farm,'Inventory').status_code==200
    response=farm.client.delete(f'/api/v1/inventory/{farm.ids["Inventory"]}/permanent',headers=farm.headers['manager'])
    assert response.status_code==204,response.text
    with Session(farm.engine) as db:
        assert db.get(InventoryItem,farm.ids['Inventory']) is None
        assert db.get(Crop,farm.ids['Crop']) is not None


def test_historical_report_snapshot_references_prevent_source_deletion(archive_farm):
    farm=archive_farm;assert post(farm,'Inventory').status_code==200
    with Session(farm.engine) as db:
        db.get(FarmReport,farm.ids['Report']).snapshot_json=json.dumps({'inventory':[{'item_code':'ARC-INV'}]});db.commit()
    result=farm.client.delete(f'/api/v1/archives/Inventory/{farm.ids["Inventory"]}',headers=farm.headers['manager'])
    assert result.status_code==409,result.text


def test_archived_resources_reject_editing_and_record_names_are_canonical(archive_farm):
    farm=archive_farm;assert post(farm,'Inventory').status_code==200
    result=farm.client.put(f'/api/v1/inventory/{farm.ids["Inventory"]}',json={'name':'Changed'},headers=farm.headers['manager'])
    assert result.status_code==400,result.text
    row=farm.client.get('/api/v1/archives',params={'module':'Inventory'},headers=farm.headers['manager']).json()['items'][0]
    assert row['recordName']=='Archive feed (ARC-INV)'


def test_user_edit_cannot_bypass_archive_reason_or_read_only_policy(archive_farm):
    farm=archive_farm;path=f'/api/v1/users/{farm.ids["User"]}'
    assert farm.client.put(path,json={'status':'Archived'},headers=farm.headers['manager']).status_code==409
    assert post(farm,'User').status_code==200
    assert farm.client.put(path,json={'full_name':'Changed archived name'},headers=farm.headers['manager']).status_code==409


def test_clients_cannot_forge_authoritative_archive_metadata(archive_farm):
    from app.routers import audit
    farm=archive_farm;farm.client.app.include_router(audit.router)
    response=farm.client.post('/api/v1/audit-logs',json={'event_type':'archive','action':'Archived','module':'Crop','entity_id':str(farm.ids['Crop']),'details':'Forged'},headers=farm.headers['manager'])
    assert response.status_code==422,response.text
    assert ledger_count(farm,'Crop')==0


def test_zero_stock_item_with_open_resource_work_must_be_reassigned_first(archive_farm):
    farm=archive_farm
    with Session(farm.engine) as db:
        db.get(FarmActivity,farm.tasks['Crop']).planned_inventory_item_id=farm.ids['Inventory'];db.commit()
    result=post(farm,'Inventory');assert result.status_code==409,result.text
    assert ledger_count(farm,'Inventory')==0


def test_import_cannot_edit_or_create_an_archived_record_without_archive_policy(archive_farm):
    from app.services.import_service import _update_record, _create_record
    farm=archive_farm;assert post(farm,'Inventory').status_code==200
    with Session(farm.engine) as db:
        item=db.get(InventoryItem,farm.ids['Inventory']);actor=db.get(User,farm.users['manager'])
        with pytest.raises(ValueError,match='read-only'):_update_record(db,item,'Inventory',{'name':'Changed'},{'name':'Name'})
        with pytest.raises(ValueError,match='Archive action'):_create_record(db,'Inventory',{'is_archived':True},actor)
        assert item.name=='Archive feed'


def test_archive_live_events_follow_module_permissions_without_exposing_ledger_ids(archive_farm):
    from app.models import Role
    from app.routers.events import load_authorized_events
    farm=archive_farm;pending(farm,'Crop');assert post(farm,'Crop').status_code==200;assert post(farm,'Inventory').status_code==200
    with Session(farm.engine) as db:
        role=Role(name='Archive Crop Viewer',is_active=True);role.set_permissions(['crops:view'])
        viewer=User(user_code='ARC-VIEW',username='archive.viewer',full_name='Archive Viewer',password_hash='test-only',status='Active',role=role)
        db.add(viewer);db.commit()
        notices,_=load_authorized_events(db,viewer,None,0)
        archive_notices=[row for row in notices if row['entity_type'].startswith('Archive:')]
        assert archive_notices and {row['entity_type'] for row in archive_notices}=={'Archive:Crop'}
        assert all(row['entity_id'] is None and row['modules']==['archives'] for row in archive_notices)
        from app.services.archive_service import list_archives
        result=list_archives(db,viewer)
        assert result['counts']=={'Crop':1} and all(row['module']=='Crop' and not row['canRestore'] and not row['canDelete'] for row in result['items'])


def test_archive_badge_counts_do_not_load_history_or_report_snapshots(archive_farm):
    farm=archive_farm;pending(farm,'Crop')
    assert post(farm,'Crop').status_code==200
    assert post(farm,'Report').status_code==200
    with patch('app.services.archive_service.latest_events',side_effect=AssertionError('Counts must not read the audit history')):
        result=farm.client.get('/api/v1/archives',params={'counts_only':True},headers=farm.headers['manager'])
        assert result.status_code==200,result.text
        data=result.json()
        assert data['items']==[] and data['counts']['Crop']==1 and data['counts']['Task']==1 and data['counts']['Report']==1
        assert data['total']==3


@pytest.mark.parametrize('module', ['Crop','Livestock','Inventory','Report'])
def test_archive_saved_page_recovers_when_records_fit_an_earlier_page(archive_farm,module):
    farm=archive_farm
    if module in {'Crop','Livestock'}: pending(farm,module)
    assert post(farm,module).status_code==200
    result=farm.client.get('/api/v1/archives',params={'module':module,'offset':25,'limit':25},headers=farm.headers['manager'])
    assert result.status_code==200,result.text
    data=result.json()
    assert data['total']==1 and data['offset']==0
    assert len(data['items'])==1 and data['items'][0]['sourceId']==farm.ids[module]


def test_preexisting_archived_eggplant_is_listed_without_any_new_archive_event(archive_farm):
    farm=archive_farm
    with Session(farm.engine) as db:
        crop=db.get(Crop,farm.ids['Crop']);crop.name='Eggplant';crop.crop_code='CRP-1027';crop.is_archived=True;db.commit()
    for query in ({'module':'Crop','counts_only':True},{'module':'Crop','offset':25,'limit':25},{}):
        result=farm.client.get('/api/v1/archives',params=query,headers=farm.headers['manager'])
        assert result.status_code==200,result.text
        data=result.json();assert data['counts']['Crop']==1
        if not query.get('counts_only'):
            row=next(row for row in data['items'] if row['module']=='Crop')
            assert row['recordName']=='Eggplant (CRP-1027)' and row['archivedDate'] is None
            assert row['archivedBy']=='Not recorded' and row['reason']=='Not recorded'
    assert ledger_count(farm,'Crop')==0
