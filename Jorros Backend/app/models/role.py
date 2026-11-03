from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base
from app.services.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    normalize_permissions,
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    permissions_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="role"
    )

    @property
    def permissions(self) -> list[str]:
        if self.permissions_json:
            try:
                value = json.loads(self.permissions_json)
                if isinstance(value, list):
                    return [str(item) for item in value]
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        return list(DEFAULT_ROLE_PERMISSIONS.get(self.name, []))

    def set_permissions(self, permissions: list[str]) -> None:
        self.permissions_json = json.dumps(
            normalize_permissions(permissions)
        )
