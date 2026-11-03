"""Expose the linked protocol version alongside crop/livestock records."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CareTemplate


def attach_care_protocol_summaries(db: Session, records: list) -> list:
    ids = sorted({record.care_template_id for record in records if record.care_template_id})
    templates = {}
    # SQL Server limits a statement to 2,100 bound parameters.
    for offset in range(0, len(ids), 500):
        for template in db.scalars(select(CareTemplate).where(CareTemplate.id.in_(ids[offset:offset + 500]))):
            templates[template.id] = template
    for record in records:
        template = templates.get(record.care_template_id)
        record.care_protocol_name = template.name if template else None
        record.care_protocol_version = template.version if template else None
        record.care_protocol_status = template.status if template else None
    return records
