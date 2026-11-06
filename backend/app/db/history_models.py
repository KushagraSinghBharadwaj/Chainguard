"""Per-client analysis history. Stores a pointer and a short summary, no user identity."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

import app.db.models  # noqa: F401  (registers the clients table for the foreign key)
from app.db.base import Base
from app.db.models import TIMESTAMPTZ


class ClientHistory(Base):
    __tablename__ = "client_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
