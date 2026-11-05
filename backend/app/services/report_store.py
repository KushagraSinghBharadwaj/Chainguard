"""Shared cache of completed reports (analysis_reports). Contains no user identity."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisReport

# Initial guesses, not measured.
FULL_TTL = timedelta(hours=1)
DEGRADED_TTL = timedelta(minutes=5)


def ttl_for(report: dict[str, Any]) -> timedelta:
    """Short TTL when the report is built on missing or interrupted data, so an outage
    is retried soon instead of being served as the answer."""
    degraded = report["risk_level"] == "INSUFFICIENT_DATA" or any(
        c["status"] in ("partial", "unavailable") for c in report["coverage"]
    )
    return DEGRADED_TTL if degraded else FULL_TTL


def get_fresh(
    db: Session, chain_id: int, subject_type: str, subject_key: str, engine_version: str
) -> dict[str, Any] | None:
    row = db.execute(
        select(AnalysisReport)
        .where(
            AnalysisReport.chain_id == chain_id,
            AnalysisReport.subject_type == subject_type,
            AnalysisReport.subject_key == subject_key.lower(),
            AnalysisReport.engine_version == engine_version,
            AnalysisReport.expires_at > datetime.now(timezone.utc),
        )
        .order_by(AnalysisReport.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row.report if row else None


def save(db: Session, report: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        AnalysisReport(
            id=UUID(report["report_id"]),
            chain_id=report["chain_id"],
            subject_type=report["subject"]["type"],
            subject_key=report["subject"]["key"].lower(),
            risk_level=report["risk_level"],
            report=report,
            engine_version=report["engine_version"],
            model_version=report["model"]["version"],
            expires_at=now + ttl_for(report),
        )
    )
    db.commit()
