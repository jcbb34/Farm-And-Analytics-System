"""Stale forms fail atomically; ordinary fresh edits and concurrent ORM writes stay safe."""
import importlib.util
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
import test_data_display_pages as support
from app.models import AuditLog, Crop, InventoryItem, Livestock
from app.routers import inventory
from app.core.exception_handlers import stale_record_handler


@pytest.fixture
def versioned():
    site = support.DataDisplayPagesTests(methodName="runTest"); site.setUp()
    site.client.app.include_router(inventory.router)
    site.client.app.add_exception_handler(StaleDataError, stale_record_handler)
    with Session(site.engine) as db:
        rows = {"crops": site.crop(500), "livestock": site.animal(500), "inventory": InventoryItem(
            item_code="INV-VERSION", name="Original feed", category="Livestock Feed", quantity=100, unit="kg",
            reorder_level=1, cost=1, supplier="Test", date_acquired=site.today, location="Storage")}
        db.add_all(rows.values()); db.commit()
        site.record_ids = {key: row.id for key, row in rows.items()}
    yield site
    site.tearDown()


@pytest.mark.parametrize("module,model,field", [("crops", Crop, "name"), ("livestock", Livestock, "record_name"), ("inventory", InventoryItem, "name")])
def test_two_clerks_cannot_overwrite_the_newer_saved_record(versioned, module, model, field):
    site = versioned; identifier = site.record_ids[module]
    url = f"/api/v1/{module}/{identifier}"; headers = site.headers("ADMIN")
    first = site.client.get(url, headers=headers)
    assert first.status_code == 200, first.text
    original = first.json()["edit_version"]
    with Session(site.engine) as db:
        row = db.get(model, identifier)
        assert row.edit_version == original, "Reading a form must not return an uncommitted version"
        setattr(row, field, "Other clerk's saved value"); db.commit()
        newer = row.edit_version
        audit_count = len(db.scalars(select(AuditLog)).all())
    response = site.client.put(url, headers=headers, json={field: "Outdated form", "expected_version": original})
    assert response.status_code == 409, response.text
    assert response.headers["x-record-conflict"] == "RECORD_CONFLICT"
    with Session(site.engine) as db:
        row = db.get(model, identifier)
        assert getattr(row, field) == "Other clerk's saved value" and row.edit_version == newer
        assert len(db.scalars(select(AuditLog)).all()) == audit_count
    current = site.client.get(url, headers=headers).json()
    response = site.client.put(url, headers=headers, json={field: "Reviewed fresh edit", "expected_version": current["edit_version"]})
    assert response.status_code == 200, response.text
    assert response.json()[field] == "Reviewed fresh edit"
    assert response.json()["edit_version"] > newer


@pytest.mark.parametrize("module", ["crops", "livestock", "inventory"])
def test_missing_version_cannot_bypass_edit_protection(versioned, module):
    site = versioned; identifier = site.record_ids[module]
    field = "record_name" if module == "livestock" else "name"
    response = site.client.put(f"/api/v1/{module}/{identifier}", headers=site.headers("ADMIN"), json={field: "Unversioned edit"})
    assert response.status_code == 428, response.text
    assert response.headers["x-record-conflict"] == "RECORD_VERSION_REQUIRED"
    model = {"crops": Crop, "livestock": Livestock, "inventory": InventoryItem}[module]
    with Session(site.engine) as db: assert getattr(db.get(model, identifier), field) != "Unversioned edit"


def test_inventory_consumption_invalidates_an_open_metadata_form(versioned):
    site = versioned; identifier = site.record_ids["inventory"]
    with Session(site.engine) as db:
        item = db.get(InventoryItem, identifier); original = item.edit_version
        item.quantity -= 5; db.commit()
    response = site.client.put(f"/api/v1/inventory/{identifier}", headers=site.headers("ADMIN"), json={"name": "Old metadata", "expected_version": original})
    assert response.status_code == 409
    with Session(site.engine) as db: assert float(db.get(InventoryItem, identifier).quantity) == 95


def test_orm_version_check_closes_the_race_after_initial_validation(versioned):
    site = versioned; identifier = site.record_ids["inventory"]
    one, two = Session(site.engine), Session(site.engine)
    try:
        first, stale = one.get(InventoryItem, identifier), two.get(InventoryItem, identifier)
        first.name = "Winning save"; one.commit()
        stale.name = "Racing save"
        with pytest.raises(StaleDataError): two.commit()
        two.rollback()
        with Session(site.engine) as db: assert db.get(InventoryItem, identifier).name == "Winning save"
    finally: one.close(); two.close()


def test_version_migration_preserves_existing_data_and_backfills_one():
    path = Path(__file__).parents[1]/"migrations/versions/a7b8c9d0e1f2_record_edit_versions.py"
    spec = importlib.util.spec_from_file_location("record_version_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for table in ["crops", "livestock", "inventory_items"]:
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)"))
            connection.execute(text(f"INSERT INTO {table} VALUES (1, 'Retained record')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            for table in ["crops", "livestock", "inventory_items"]:
                assert connection.execute(text(f"SELECT name, edit_version FROM {table}")).one() == ("Retained record", 1)
            migration.downgrade()
        for table in ["crops", "livestock", "inventory_items"]:
            assert "edit_version" not in {column["name"] for column in inspect(connection).get_columns(table)}
            assert connection.execute(text(f"SELECT name FROM {table}")).scalar_one() == "Retained record"
    engine.dispose()


def test_concurrent_flush_conflict_is_an_actionable_http_response(versioned):
    @versioned.client.app.get("/synthetic-racing-update")
    def racing_update():
        raise StaleDataError("Synthetic internal database details")
    response = versioned.client.get("/synthetic-racing-update")
    assert response.status_code == 409
    assert response.json()["code"] == "RECORD_CONFLICT"
    assert "Synthetic internal" not in response.text
