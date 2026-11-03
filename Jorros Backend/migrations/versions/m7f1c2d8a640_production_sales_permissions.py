"""production sales permission separation

Revision ID: m7f1c2d8a640
Revises: l6e3a9c4f120
Create Date: 2026-08-16 21:10:00.000000
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "m7f1c2d8a640"
down_revision: Union[str, Sequence[str], None] = "l6e3a9c4f120"
branch_labels = None
depends_on = None


def _load_permissions(value) -> list[str] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, list):
        return None
    return sorted({str(item).strip() for item in parsed if str(item).strip()})


def _save_permissions(bind, role_id: int, permissions: list[str]) -> None:
    bind.execute(
        sa.text("UPDATE roles SET permissions_json=:permissions WHERE id=:role_id"),
        {
            "permissions": json.dumps(sorted(set(permissions))),
            "role_id": int(role_id),
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, name, permissions_json FROM roles "
            "WHERE name IN ('Farm Staff', 'Viewer')"
        )
    ).mappings().all()

    for row in rows:
        permissions = _load_permissions(row["permissions_json"])
        # A NULL/invalid permissions_json intentionally falls back to the
        # application's built-in role defaults, which already include the new
        # Production & Sales permissions. Do not replace that fallback with a
        # partial list here.
        if permissions is None:
            continue

        existing = set(permissions)
        if "*" in existing:
            continue

        if "crops:view" in existing or "livestock:view" in existing:
            existing.add("production_sales:view")
        if row["name"] == "Farm Staff" and (
            "crops:update" in existing or "livestock:update" in existing
        ):
            existing.add("production_sales:update")

        _save_permissions(bind, row["id"], sorted(existing))


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, permissions_json FROM roles "
            "WHERE name IN ('Farm Staff', 'Viewer')"
        )
    ).mappings().all()

    for row in rows:
        permissions = _load_permissions(row["permissions_json"])
        if permissions is None:
            continue
        filtered = [
            item
            for item in permissions
            if item not in {"production_sales:view", "production_sales:update"}
        ]
        _save_permissions(bind, row["id"], filtered)
