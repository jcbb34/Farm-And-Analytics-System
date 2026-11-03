from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UnicodeText, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class VoidOperation(Base):
    """One completed record-bound authorization. No passwords or OTPs are stored."""
    __tablename__ = 'void_operations'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    requester_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    authorizer_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    record_id: Mapped[int] = mapped_column(nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
