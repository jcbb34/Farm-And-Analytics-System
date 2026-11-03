from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_scheduler_has_leader_election_metrics_and_health_contract():
    scheduler = source("app/services/farm_automation_scheduler.py")
    main = source("app/main.py")

    assert "try_acquire_session_lock" in scheduler
    assert "FARM_AUTOMATION_LEADER_GUARD" in scheduler
    assert "session_lock_is_held" in scheduler
    assert "run_id = str(uuid4())" in scheduler
    assert "duration_ms" in scheduler
    assert '"generated"' in scheduler
    assert '"resolved"' in scheduler
    assert '"errors"' in scheduler
    assert "last_success_at" in scheduler
    assert "def scheduler_health" in scheduler
    assert '@app.get("/api/v1/health/scheduler")' in main
    assert not re.search(r"\bprint\s*\(", scheduler)


def test_scheduler_queries_and_migration_expose_due_indexes():
    tasks = source("app/services/task_engine.py")
    alerts = source("app/services/alert_engine.py")
    migration = source("migrations/versions/q9e5n2t8b014_scheduler_hardening.py")

    assert "LivestockReproductionRecord.actual_date.is_(None)" in tasks
    assert "LivestockReproductionRecord.expected_date" in tasks
    assert "InventoryItem.quantity <= InventoryItem.reorder_level" in tasks
    assert "InventoryItem.quantity <= InventoryItem.reorder_level" in alerts
    assert "FarmAlert.status == \"Active\"" in alerts

    for index_name in (
        "ix_farm_activities_scheduler_due",
        "ix_farm_alerts_scheduler_active",
        "ix_crops_scheduler_harvest_due",
        "ix_livestock_scheduler_vaccination_due",
        "ix_inventory_items_scheduler_low_stock",
        "ix_livestock_reproduction_scheduler_due",
        "ix_crop_growth_records_latest",
    ):
        assert index_name in migration


def test_task_codes_use_transactional_counter_instead_of_history_scan():
    counter = source("app/services/code_counter_service.py")
    activities = source("app/routers/activities.py")
    task_engine = source("app/services/task_engine.py")
    workforce = source("app/routers/workforce_handlers.py")

    assert "with_for_update()" in counter
    assert "func.max(seed_model.id)" in counter
    assert "code_column == f\"{normalized_prefix}-{value}\"" in counter
    assert "while db.scalar(" in counter
    assert "next_record_code(" in activities
    assert "next_record_code(" in task_engine
    assert "next_record_code(" in workforce
    assert re.search(r"scanning and\s+parsing every historical code", counter)
    assert '"ACT": "activity"' in workforce


def test_workforce_routes_are_owned_by_explicit_domain_modules():
    route_root = ROOT / "app/routers/workforce_routes"
    expected = {
        "employees.py",
        "task_lifecycle.py",
        "assignments.py",
        "attendance_leave.py",
        "evidence.py",
        "care_protocols.py",
        "resource_posting.py",
    }
    assert expected.issubset({path.name for path in route_root.glob("*.py")})

    facade = source("app/routers/workforce.py")
    assert "DOMAIN_ROUTERS" in facade
    assert "do not cover the compatibility API exactly" in facade
