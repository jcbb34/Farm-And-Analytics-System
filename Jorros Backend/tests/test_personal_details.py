"""HTTP coverage for structured identity, local address references and legacy records."""
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_resource_monitoring import farm
from app.models import Employee, Role, User
from app.routers import users, locations
from app.services.location_reference import catalogue


def details(**changes):
    return {'first_name':'  María  Ana ','middle_name':'Reyes','surname':'De la Cruz','suffix':'Jr.',
            'address':{'street':'12 Sample Street','subdivision':'Sample Village','province':'Custom Province',
                       'city':'Custom Municipality','barangay':'Custom Barangay','postal_code':'0450'},**changes}


def schedule(farm):
    return {'effective_from':str(farm.today),'days':[
        {'day_of_week':day,'state':'Working Day' if day<5 else 'Rest Day',
         'start_time':'08:00' if day<5 else None,'end_time':'17:00' if day<5 else None} for day in range(7)]}


@pytest.fixture
def people(farm):
    farm.client.app.include_router(users.router);farm.client.app.include_router(locations.router)
    with Session(farm.engine) as db:
        role=Role(name='Employee',is_active=True);role.set_permissions(['workforce:submit']);db.add(role);db.commit()
    return farm


def create(people,kind,personal_details,**changes):
    payload={'full_name':'Untrusted full name','personal_details':personal_details}
    if kind=='employee':
        payload.update({'position':'Farm worker','weekly_schedule':schedule(people),**changes});path='/api/v1/workforce/employees'
    else:
        payload.update({'username':'identity.test','password':'Synthetic-Test-Password','role_name':'Employee',**changes});path='/api/v1/users'
    return people.client.post(path,json=payload,headers=people.headers['manager'])


@pytest.mark.parametrize('kind',['employee','user'])
def test_split_name_and_custom_address_survive_reload(people,kind):
    response=create(people,kind,details());assert response.status_code==201,response.text
    record=response.json();assert record['full_name']=='María Ana Reyes De la Cruz Jr.'
    assert record['personal_details']['address']['postal_code']=='0450'
    path=f'/api/v1/{"workforce/employees" if kind=="employee" else "users"}/{record["id"]}'
    reloaded=next(row for row in people.client.get('/api/v1/workforce/employees',headers=people.headers['manager']).json() if row['id']==record['id']) if kind=='employee' else people.client.get(path,headers=people.headers['manager']).json()
    assert reloaded['personal_details']==record['personal_details']
    with Session(people.engine) as db:
        saved=db.get(Employee if kind=='employee' else User,record['id'])
        assert saved.personal_details['surname']=='De la Cruz'
        if kind=='employee':assert saved.address=='12 Sample Street, Sample Village, Custom Barangay, Custom Municipality, Custom Province, 0450'


@pytest.mark.parametrize('kind',['employee','user'])
def test_optional_fields_can_be_cleared(people,kind):
    record=create(people,kind,details()).json()
    path=f'/api/v1/{"workforce/employees" if kind=="employee" else "users"}/{record["id"]}'
    response=people.client.put(path,json={'personal_details':details(middle_name=None,suffix=None,address=None)},headers=people.headers['manager'])
    assert response.status_code==200,response.text
    assert response.json()['full_name']=='María Ana De la Cruz'
    assert response.json()['personal_details']['address'] is None


def test_legacy_details_are_not_guessed_or_erased(people):
    record=create(people,'employee',None,full_name='Maria del Carmen de la Cruz',address='Original house and barangay').json()
    path=f'/api/v1/workforce/employees/{record["id"]}'
    response=people.client.put(path,json={'notes':'Updated note'},headers=people.headers['manager'])
    assert response.status_code==200 and response.json()['personal_details'] is None
    assert response.json()['full_name']=='Maria del Carmen de la Cruz'
    assert response.json()['address']=='Original house and barangay'
    renamed=people.client.put(path,json={'personal_details':details(address=None)},headers=people.headers['manager'])
    assert renamed.json()['address']=='Original house and barangay'


def test_legacy_user_rename_clears_stale_split_names(people):
    record=create(people,'user',details()).json()
    response=people.client.put(f'/api/v1/users/{record["id"]}',json={'full_name':'Changed Legacy Name'},headers=people.headers['manager'])
    assert response.status_code==200 and response.json()['full_name']=='Changed Legacy Name'
    assert response.json()['personal_details']['first_name'] is None
    assert response.json()['personal_details']['address']['city']=='Custom Municipality'


@pytest.mark.parametrize('bad',[details(first_name=''),details(surname=None),details(suffix='Dr.'),
    details(address={'province':'Albay','city':'Legazpi','barangay':'Test','postal_code':'450'}),
    details(address={'street':'Only a street'}),details(first_name='A'*60,middle_name='B'*60,surname='C'*60)])
def test_invalid_details_do_not_insert(people,bad):
    with Session(people.engine) as db:before=len(db.query(Employee).all())
    response=create(people,'employee',bad);assert response.status_code==422,response.text
    with Session(people.engine) as db:assert len(db.query(Employee).all())==before


def test_official_codes_canonicalize_names_and_reject_mismatched_parents(people):
    data=catalogue();province=next(r for r in data['provinces'] if r['name']=='Albay')
    city=next(r for r in data['cities'] if 'Legazpi' in r['name']);barangay=next(r for r in data['barangays'] if r['city_code']==city['code'])
    address={f'{name}_code':row['code'] for name,row in [('province',province),('city',city),('barangay',barangay)]}
    address.update({'province':'Forged province','city':'Forged city','barangay':'Forged barangay'})
    response=create(people,'employee',details(address=address));assert response.status_code==201,response.text
    assert response.json()['personal_details']['address']['city']==city['name']
    address['province_code']='1300000000';assert create(people,'employee',details(address=address)).status_code==422
    address['province_code']=None;assert create(people,'employee',details(address=address)).status_code==422


def test_offline_reference_includes_manila_and_filters_children(people):
    assert len(catalogue()['barangays'])==42010
    city=next(r for r in catalogue()['cities'] if r['name']=='City of Manila')
    response=people.client.get('/api/v1/reference/locations',params={'level':'barangays','parent_code':city['code']},headers=people.headers['worker'])
    assert response.status_code==200 and len(response.json()['items'])>800
    assert people.client.get('/api/v1/reference/locations',params={'level':'cities'},headers=people.headers['manager']).json()['items']==[]
    assert people.client.get('/api/v1/reference/locations',params={'level':'provinces'}).status_code==401


def test_employee_login_mirrors_details(people):
    response=create(people,'employee',details(),create_login_account=True,login_username='linked.identity',login_password='Synthetic-Test-Password')
    assert response.status_code==201,response.text
    record=response.json()
    with Session(people.engine) as db:assert db.get(User,record['login_user_id']).personal_details==record['personal_details']
    changed=people.client.put(f'/api/v1/workforce/employees/{record["id"]}',json={'personal_details':details(surname="O'Connor",suffix='III')},headers=people.headers['manager'])
    assert changed.status_code==200,changed.text
    with Session(people.engine) as db:assert db.get(User,record['login_user_id']).full_name=="María Ana Reyes O'Connor III"


def test_private_profile_permissions_remain_enforced(people):
    response=people.client.put(f'/api/v1/workforce/employees/{people.employees["other"]}',json={'personal_details':details()},headers=people.headers['worker'])
    assert response.status_code==403
    assert people.client.get('/api/v1/users',headers=people.headers['worker']).status_code==403


def test_migration_preserves_existing_records():
    path=Path(__file__).resolve().parents[1]/'migrations/versions/d4e5f6a7b8c9_personal_details_and_void_authorization.py'
    spec=importlib.util.spec_from_file_location('personal_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision=='c3d4e5f6a7b8'
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, full_name VARCHAR(120))')
        connection.exec_driver_sql('CREATE TABLE employees (id INTEGER PRIMARY KEY, full_name VARCHAR(120), address VARCHAR(255))')
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'Legacy User')")
        connection.exec_driver_sql("INSERT INTO employees VALUES (1, 'Legacy Employee', 'Legacy Address')")
        with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
        assert connection.execute(text('SELECT full_name,address,personal_details_json FROM employees')).one()==('Legacy Employee','Legacy Address',None)
        assert connection.execute(text('SELECT full_name,personal_details_json FROM users')).one()==('Legacy User',None)
        assert 'void_operations' in inspect(connection).get_table_names()
    engine.dispose()


def test_structured_address_overrides_a_stale_legacy_address_field(people):
    record=create(people,'employee',details()).json()
    updated=details(address={'province':'New custom province','city':'New custom city','barangay':'New custom barangay','postal_code':'4500'})
    response=people.client.put(f'/api/v1/workforce/employees/{record["id"]}',json={'personal_details':updated,'address':record['address']},headers=people.headers['manager'])
    assert response.status_code==200,response.text
    assert response.json()['address']=='New custom barangay, New custom city, New custom province, 4500'


@pytest.mark.parametrize('kind',['employee','user'])
def test_new_structured_profile_cannot_bypass_required_name_parts(people,kind):
    assert create(people,kind,{'address':details()['address']}).status_code==422


def test_reference_preserves_names_with_a_windows_default_encoding(people, monkeypatch):
    """The published UTF-8 catalogue must not depend on the host's code page."""
    data_path = Path(__file__).resolve().parents[1] / 'reference_data/philippine_locations.json'
    original_open = Path.open

    def windows_open(path, *args, **kwargs):
        if path == data_path and kwargs.get('encoding') in (None, 'locale'):
            kwargs['encoding'] = 'cp1252'
        return original_open(path, *args, **kwargs)

    catalogue.cache_clear()
    monkeypatch.setattr(Path, 'open', windows_open)
    try:
        response = people.client.get('/api/v1/reference/locations',
            params={'level': 'cities', 'parent_code': '0201500000'}, headers=people.headers['manager'])
        assert response.status_code == 200, response.text
        names = [row['name'] for row in response.json()['items']]
        assert 'Peñablanca' in names
        assert not any('Ã' in name for name in names)
    finally:
        catalogue.cache_clear()


def test_main_application_serves_the_complete_address_hierarchy(farm):
    """Exercise the production router registration, not a hand-built reference app."""
    from fastapi.testclient import TestClient
    from app.core.database import get_db
    from app.main import app

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = farm.client.app.dependency_overrides[get_db]
    # No lifespan context: this isolated check must not start production schedulers.
    client = TestClient(app)
    try:
        path = '/api/v1/reference/locations'
        assert client.get(path, params={'level': 'provinces'}).status_code == 401
        provinces = client.get(path, params={'level': 'provinces'}, headers=farm.headers['manager'])
        assert provinces.status_code == 200, provinces.text
        assert len(provinces.json()['items']) == 84
        albay = next(row for row in provinces.json()['items'] if row['name'] == 'Albay')
        cities = client.get(path, params={'level': 'cities', 'parent_code': albay['code']}, headers=farm.headers['manager'])
        assert cities.status_code == 200, cities.text
        legazpi = next(row for row in cities.json()['items'] if 'Legazpi' in row['name'])
        barangays = client.get(path, params={'level': 'barangays', 'parent_code': legazpi['code']}, headers=farm.headers['manager'])
        assert barangays.status_code == 200, barangays.text
        assert any('Gogon' in row['name'] for row in barangays.json()['items'])
    finally:
        client.close()
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
