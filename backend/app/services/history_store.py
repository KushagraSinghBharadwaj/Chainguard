"""Record and list a client's past analyses. Recording must never break an analysis."""

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.history_models import ClientHistory

logger = logging.getLogger("chainguard.history")


def _uuid_or_none(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def record(db: Session, client_id: UUID, report: dict[str, Any]) -> None:
    try:
        subject = report.get("subject") or {}
        db.add(
            ClientHistory(
                id=uuid4(),
                client_id=client_id,
                report_id=_uuid_or_none(report.get("report_id")),
                chain_id=int(report["chain_id"]),
                subject_type=str(subject["type"]),
                subject_key=str(subject["key"]).lower(),
                risk_level=str(report["risk_level"]),
                engine_version=str(report.get("engine_version", "")),
                summary=report.get("summary"),
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "history not recorded",
            extra={"extra_fields": {"error_class": type(exc).__name__}},
        )


def list_for_client(db: Session, client_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ClientHistory)
        .where(ClientHistory.client_id == client_id)
        .order_by(ClientHistory.created_at.desc())
        .limit(limit)
    ).scalars()
    return [
        {
            "report_id": str(r.report_id) if r.report_id else None,
            "chain_id": r.chain_id,
            "subject_type": r.subject_type,
            "subject_key": r.subject_key,
            "risk_level": r.risk_level,
            "engine_version": r.engine_version,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
