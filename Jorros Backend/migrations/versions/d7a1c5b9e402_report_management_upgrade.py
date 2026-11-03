"""report approval comparison insights and revisions

Revision ID: d7a1c5b9e402
Revises: c6f2a94e8d31
Create Date: 2026-08-11 20:33:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7a1c5b9e402"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "c6f2a94e8d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "farm_reports",
        sa.Column(
            "comparison_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "findings_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "recommendations_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "data_quality_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "reviewed_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "reviewed_by_name",
            sa.String(
                length=150
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "approved_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "archived_from_status",
            sa.String(
                length=30
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "revision_group_code",
            sa.String(
                length=30
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "revision_number",
            sa.Integer(),
            server_default=sa.text(
                "1"
            ),
            nullable=False,
        ),
    )

    op.add_column(
        "farm_reports",
        sa.Column(
            "revision_of_report_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_farm_reports_reviewed_by_user_id_users",
        "farm_reports",
        "users",
        [
            "reviewed_by_user_id"
        ],
        [
            "id"
        ],
    )

    op.create_foreign_key(
        "fk_farm_reports_revision_of_report_id_farm_reports",
        "farm_reports",
        "farm_reports",
        [
            "revision_of_report_id"
        ],
        [
            "id"
        ],
    )

    op.create_index(
        op.f(
            "ix_farm_reports_revision_group_code"
        ),
        "farm_reports",
        [
            "revision_group_code"
        ],
        unique=False,
    )

    # Existing legacy "Completed" reports enter the review queue under
    # the new approval workflow. Archived reports stay archived.
    op.execute(
        """
        UPDATE farm_reports
        SET status = 'For Review', submitted_at = GETDATE()
        WHERE status = 'Completed'
        """
    )

    op.execute(
        """
        UPDATE farm_reports
        SET revision_group_code = report_code
        WHERE revision_group_code IS NULL
        """
    )

    # Force the next preview/download to use the upgraded professional
    # PDF template and regenerate analysis from the saved snapshot.
    op.execute(
        """
        UPDATE farm_reports
        SET pdf_filename = NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_farm_reports_revision_group_code"
        ),
        table_name="farm_reports",
    )

    op.drop_constraint(
        "fk_farm_reports_revision_of_report_id_farm_reports",
        "farm_reports",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_farm_reports_reviewed_by_user_id_users",
        "farm_reports",
        type_="foreignkey",
    )

    for column in [
        "revision_of_report_id",
        "revision_number",
        "revision_group_code",
        "archived_from_status",
        "approved_at",
        "reviewed_by_name",
        "reviewed_by_user_id",
        "submitted_at",
        "data_quality_json",
        "recommendations_json",
        "findings_json",
        "comparison_json",
    ]:
        op.drop_column(
            "farm_reports",
            column,
        )
