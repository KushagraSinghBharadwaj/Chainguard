"""Calls a local Ollama server to rephrase an engine summary.

Fails open: if anything goes wrong (disabled, slow, error, text rejected by the
validator) it returns None and the caller keeps showing the engine summary.
"""

import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.explain import (
    build_messages,
    build_source_text,
    should_explain,
    validate_explanation,
)

log = logging.getLogger("chainguard.explain")


async def generate_explanation(
    report: dict[str, Any],
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    if not cfg.llm_enabled or not should_explain(report):
        return None

    payload = {
        "model": cfg.ollama_model,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 120},
        "messages": build_messages(report),
    }
    url = cfg.ollama_url.rstrip("/") + "/api/chat"
    try:
        async with httpx.AsyncClient(timeout=cfg.llm_timeout_seconds, transport=transport) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            text = resp.json()["message"]["content"]
    except Exception as exc:  # fail open on any problem
        log.warning("explanation skipped: %s", type(exc).__name__)
        return None

    ok, reason = validate_explanation(
        text, level=report["risk_level"], source_text=build_source_text(report)
    )
    if not ok:
        log.info("explanation rejected: %s", reason)
        return None
    return {
        "text": text.strip(),
        "model": cfg.ollama_model,
        "source": "local-llm",
        "validated": True,
    }

def generate_explanation_sync(
    report: dict[str, Any], *, settings: Settings | None = None
) -> dict[str, Any] | None:
    """Sync wrapper for sync routes. Never raises."""
    import asyncio

    cfg = settings or get_settings()
    if not cfg.llm_enabled or not should_explain(report):
        return None
    try:
        return asyncio.run(generate_explanation(report, settings=cfg))
    except Exception as exc:
        log.warning("explanation skipped: %s", type(exc).__name__)
        return None