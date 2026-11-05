import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RISK_LEVELS = ("LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA")
TIMESTAMPTZ = DateTime(timezone=True)


class Chain(Base):
    __tablename__ = "chains"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    native_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class Client(Base):
    """One row per extension install. No user identity is stored (decision D2)."""

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)


class ClientToken(Base):
    """Rotating bearer tokens. Only the SHA-256 hash is stored, never the token."""

    __tablename__ = "client_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clients.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)


class ProviderCache(Base):
    """Raw public provider responses. Failed calls are never cached as empty results."""

    __tablename__ = "provider_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, index=True)


class IntelSource(Base):
    __tablename__ = "intel_sources"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    license_note: Mapped[str | None] = mapped_column(Text)
    version_label: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)


class IntelEntry(Base):
    """Downloaded denylist data. Each refresh replaces a source's rows in one transaction."""

    __tablename__ = "intel_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("intel_sources.id"), nullable=False
    )
    chain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chains.chain_id"))
    address: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "chain_id",
            "address",
            "domain",
            "category",
            name="uq_intel_entries_entry",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "address IS NULL OR address ~ '^0x[0-9a-f]{40}$'",
            name="address_lowercase_hex",
        ),
        CheckConstraint("address IS NOT NULL OR domain IS NOT NULL", name="address_or_domain"),
        Index("ix_intel_entries_chain_address", "chain_id", "address"),
    )


class AnalysisReport(Base):
    """Shared cache of completed reports. Contains no user identity."""

    __tablename__ = "analysis_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chains.chain_id"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Enum(*RISK_LEVELS, name="risk_level"), nullable=False)
    report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('wallet', 'token', 'transaction')",
            name="subject_type_valid",
        ),
    )


Index(
    "ix_analysis_reports_lookup",
    AnalysisReport.chain_id,
    AnalysisReport.subject_type,
    AnalysisReport.subject_key,
    AnalysisReport.created_at.desc(),
)
