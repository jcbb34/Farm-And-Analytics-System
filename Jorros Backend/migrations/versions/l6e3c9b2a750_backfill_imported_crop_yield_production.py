"""backfill imported crop yield production

Revision ID: l6e3c9b2a750
Revises: n8c4b1e7d250
Create Date: 2026-08-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "l6e3c9b2a750"
down_revision: Union[str, Sequence[str], None] = "n8c4b1e7d250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO livestock_production_records (
            source_type, livestock_id, crop_id, crop_yield_record_id,
            output_type, record_date, period_start_date, period_end_date,
            source_head_quantity, source_female_quantity, source_active_quantity,
            gross_quantity, loss_quantity, farm_use_quantity, reserved_quantity,
            quantity, unit, quality_grade, destination, track_sale_inventory,
            notes, recorded_by_user_id, created_at
        )
        SELECT
            'Crop', NULL, y.crop_id, y.id,
            c.name, y.harvest_date, y.harvest_date, y.harvest_date,
            NULL, NULL, NULL,
            y.quantity_kg,
            COALESCE(y.damaged_quantity_kg, 0),
            COALESCE(y.farm_use_quantity_kg, 0),
            COALESCE(y.reserved_quantity_kg, 0),
            y.quantity_kg
                - COALESCE(y.damaged_quantity_kg, 0)
                - COALESCE(y.farm_use_quantity_kg, 0)
                - COALESCE(y.reserved_quantity_kg, 0),
            'kg', y.quality,
            CASE
                WHEN y.quantity_kg
                    - COALESCE(y.damaged_quantity_kg, 0)
                    - COALESCE(y.farm_use_quantity_kg, 0)
                    - COALESCE(y.reserved_quantity_kg, 0) > 0
                THEN 'Available for sale'
                ELSE 'Fully allocated / unavailable'
            END,
            CASE
                WHEN y.quantity_kg
                    - COALESCE(y.damaged_quantity_kg, 0)
                    - COALESCE(y.farm_use_quantity_kg, 0)
                    - COALESCE(y.reserved_quantity_kg, 0) > 0
                THEN 1
                ELSE 0
            END,
            y.notes, y.recorded_by_user_id, y.created_at
        FROM crop_yield_records y
        INNER JOIN crops c ON c.id = y.crop_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM livestock_production_records p
            WHERE p.crop_yield_record_id = y.id
        )
          AND y.quantity_kg
                - COALESCE(y.damaged_quantity_kg, 0)
                - COALESCE(y.farm_use_quantity_kg, 0)
                - COALESCE(y.reserved_quantity_kg, 0) >= 0
        """
    )


def downgrade() -> None:
    """Keep historical production data; the previous schema already supports it."""
    # This revision changes data only, not schema. Imported yield production
    # rows may already have sale allocations after the migration. There is no
    # reliable marker that distinguishes those rows from later edits, so
    # deleting them on downgrade would lose farm history. Retain the data;
    # the preceding schema accepts these rows unchanged.
    pass
