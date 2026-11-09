from app.core.config import Settings
from app.services.ollama_client import generate_explanation_sync

REPORT = {"risk_level": "MODERATE", "summary": "MODERATE risk. Something happened."}


def test_sync_disabled_returns_none():
    assert generate_explanation_sync(REPORT, settings=Settings(llm_enabled=False)) is None


def test_sync_low_level_returns_none():
    low = {"risk_level": "LOW", "summary": "No findings."}
    assert generate_explanation_sync(low, settings=Settings(llm_enabled=True)) is None


def test_sync_unreachable_ollama_fails_open():
    cfg = Settings(llm_enabled=True, ollama_url="http://127.0.0.1:9", llm_timeout_seconds=2)
    assert generate_explanation_sync(REPORT, settings=cfg) is None