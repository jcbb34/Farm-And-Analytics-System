"""Chronological summaries shared by manual and approved task vaccinations."""
from sqlalchemy import select

from app.models import Livestock, LivestockVaccinationRecord
from app.services.db_concurrency import acquire_transaction_lock


def lock_vaccination_parent(db, livestock_id):
    # Call after stock has been locked; both posting paths use this lock order.
    acquire_transaction_lock(db, f"livestock-vaccination-summary:{livestock_id}")
    db.flush()
    statement = select(Livestock).where(Livestock.id == livestock_id)
    if db.get_bind().dialect.name == "mssql":
        statement = statement.with_hint(Livestock, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql")
    else:
        statement = statement.with_for_update()
    return db.scalar(statement.execution_options(populate_existing=True))


def update_vaccination_summary(db, livestock, record, *, status, next_due):
    db.flush()
    latest = db.scalar(select(LivestockVaccinationRecord.id).where(
        LivestockVaccinationRecord.livestock_id == livestock.id).order_by(
        LivestockVaccinationRecord.date_administered.desc(), LivestockVaccinationRecord.id.desc()).limit(1))
    if latest == record.id:
        livestock.vaccination_status = status
        livestock.next_vaccination = next_due
    if livestock.last_checkup is None or record.date_administered > livestock.last_checkup:
        livestock.last_checkup = record.date_administered
