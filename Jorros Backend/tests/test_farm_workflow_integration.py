"""HTTP workflows across employee work, stock, production, sales and reports."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_resource_monitoring import farm, submit, review, observation
from test_remaining_workflows import item
from app.models import InventoryItem, InventoryStockRecord, Livestock, FarmReport, ResourceUsage
from app.routers import production_sales, reports
from app.services import report_pdf


@pytest.mark.parametrize('module', ['Crop', 'Livestock'])
def test_employee_approval_to_stock_sale_and_report(farm, module, tmp_path, monkeypatch):
    farm.client.app.include_router(production_sales.router)
    farm.client.app.include_router(reports.router)
    monkeypatch.setattr(report_pdf, 'REPORT_DIRECTORY', tmp_path / 'reports')
    if module == 'Livestock':
        with Session(farm.engine) as db:
            animal = db.get(Livestock, farm.ids[module])
            animal.animal_type = 'Chicken'
            animal.production_purpose = 'Egg Production'
            animal.female_quantity = 10
            db.commit()

    # The employee records observations; only the manager can post them.
    monitoring = observation(farm, module, **({'observed_stage': 'Harvest Ready'} if module == 'Crop' else {}))
    assert submit(farm, module, monitoring=monitoring)[0].status_code == 200
    assert review(farm, module, role='worker').status_code == 403
    assert review(farm, module, confirm_harvest_ready=(module == 'Crop')).status_code == 200

    inventory_id = item(farm, 'Fertilizer' if module == 'Crop' else 'Livestock Feed')
    usage_type = 'Fertilizer' if module == 'Crop' else 'Feed'
    assignment = farm.client.post('/api/v1/workforce/tasks', headers=farm.headers['manager'], json={
        'name': 'Apply fertilizer' if module == 'Crop' else 'Feed flock', 'category': f'{module} Care',
        'employee_id': farm.employees['worker'], 'activity_date': str(farm.today),
        'allow_unavailable_override': True, 'requires_evidence': False,
        'source_module': module, 'source_type': 'manual', 'source_record_id': farm.ids[module],
        'planned_inventory_item_id': inventory_id, 'planned_usage_type': usage_type,
        'planned_quantity': 2, 'planned_unit': 'kg',
    })
    assert assignment.status_code == 201, assignment.text
    task_id = assignment.json()['id']
    visible = farm.client.get('/api/v1/workforce/my-tasks', headers=farm.headers['worker'])
    assert visible.status_code == 200 and any(task['id'] == task_id for task in visible.json())
    started = farm.client.post(f'/api/v1/workforce/tasks/{task_id}/start', json={}, headers=farm.headers['worker'])
    assert started.status_code == 200, started.text
    payload = {'actual_quantity': 2, 'actual_quantity_confirmed': True,
               'actual_unit': 'kg', 'worker_notes': 'Synthetic integration test work'}
    headers = {**farm.headers['worker'], 'Idempotency-Key': f'integrated-work-{module}'}
    submitted = farm.client.post(f'/api/v1/workforce/tasks/{task_id}/submit', json=payload, headers=headers)
    assert submitted.status_code == 200, submitted.text
    with Session(farm.engine) as db:
        assert float(db.get(InventoryItem, inventory_id).quantity) == 100
    approved = farm.client.post(f'/api/v1/workforce/tasks/{task_id}/review', json={'decision': 'Approve'}, headers=farm.headers['manager'])
    assert approved.status_code == 200, approved.text
    assert farm.client.post(f'/api/v1/workforce/tasks/{task_id}/review', json={'decision': 'Approve'}, headers=farm.headers['manager']).status_code == 409
    with Session(farm.engine) as db:
        assert float(db.get(InventoryItem, inventory_id).quantity) == 98
        assert db.scalar(select(func.count()).select_from(ResourceUsage).where(ResourceUsage.activity_id == task_id)) == 1
        assert db.scalar(select(func.count()).select_from(InventoryStockRecord).where(InventoryStockRecord.inventory_item_id == inventory_id)) == 1

    if module == 'Crop':
        harvest = farm.client.post(f'/api/v1/crops/{farm.ids[module]}/yield-records', headers={
            **farm.headers['manager'], 'Idempotency-Key': 'integrated-harvest'}, json={
            'harvest_date': str(farm.today), 'quantity_kg': 10, 'harvest_type': 'Partial Harvest',
            'performed_by_employee_id': farm.employees['worker'], 'manual_reason': 'Approved test harvest',
        })
        assert harvest.status_code == 201, harvest.text
        produced = farm.client.get('/api/v1/production-sales/production', params={'crop_id': farm.ids[module]}, headers=farm.headers['manager'])
        assert produced.status_code == 200, produced.text
        production_id = produced.json()[0]['id']
    else:
        produced = farm.client.post('/api/v1/production-sales/production', headers={
            **farm.headers['manager'], 'Idempotency-Key': 'integrated-eggs'}, json={
            'livestock_id': farm.ids[module], 'output_type': 'Eggs', 'record_date': str(farm.today),
            'source_active_quantity': 10, 'gross_quantity': 10, 'quantity': 10, 'unit': 'pcs',
        })
        assert produced.status_code == 201, produced.text
        production_id = produced.json()['id']
    sale = farm.client.post('/api/v1/production-sales/sales', headers={
        **farm.headers['manager'], 'Idempotency-Key': f'integrated-sale-{module}'}, json={
        'sale_date': str(farm.today), 'items': [{'item_kind': 'Production', 'production_record_id': production_id,
                                              'quantity': 2, 'unit_price': 50}],
        'payment_status': 'Paid', 'amount_paid': 100, 'buyer_name': 'Synthetic test buyer',
    })
    assert sale.status_code == 201, sale.text
    available = farm.client.get('/api/v1/production-sales/production', headers=farm.headers['manager'])
    output = next(row for row in available.json() if row['id'] == production_id)
    assert output['available_quantity'] == 8

    for category, kind, expectations in [
        ('Inventory', 'Inventory Movement and Resource Usage', {'approved_task_usage_records': 1}),
        ('Production & Sales', 'Production and Sales Summary', {'quantity_sold': 2, 'revenue': 100, 'outstanding': 0}),
    ]:
        response = farm.client.post('/api/v1/reports', headers=farm.headers['manager'], json={
            'title': f'{module} integration {category}', 'category': category, 'report_type': kind,
            'start_date': str(farm.today), 'end_date': str(farm.today), 'prepared_by': 'Untrusted browser name',
        })
        assert response.status_code == 201, response.text
        with Session(farm.engine) as db:
            report = db.get(FarmReport, response.json()['id'])
            assert report.prepared_by == 'Monitoring manager'
            for key, expected in expectations.items():
                assert report.snapshot['metrics'][key] == expected
            assert list((tmp_path / 'reports').glob('*.pdf')), 'real PDF generation must complete'
    assert farm.client.post('/api/v1/reports', json={}, headers=farm.headers['worker']).status_code == 403
