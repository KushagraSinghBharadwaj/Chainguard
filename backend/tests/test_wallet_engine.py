"""Wallet engine tests. All provider data here is SYNTHETIC: test doubles shaped like the real
result types, with fake addresses. Nothing here is a real provider answer."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.engines.wallet import analyze_wallet
from app.providers.base import ProviderResult, Transaction
from app.services.intel_lookup import IntelHit, IntelLookup, IntelSourceInfo

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
SUBJECT = "0x" + "a" * 40
OTHER = "0x" + "d" * 40
SOURCES = (
    IntelSourceInfo("ofac_sdn", "synthetic-1", NOW),
    IntelSourceInfo("scamsniffer", "synthetic-1", NOW),
)
OFAC = IntelHit("ofac_sdn", "sanctions", "Synthetic Party", NOW, "synthetic-1")
SCAM = IntelHit("scamsniffer", "phishing", None, NOW, "synthetic-1")


def tx(i, to=OTHER):
    return Transaction(f"0x{i:064x}", i, NOW - timedelta(days=400 - i % 300), SUBJECT, to, 0, False, None, 21000)


class FakeHistory:
    def __init__(self, txs=(), fail_after=None):
        self.txs = list(txs)
        self.fail_after = fail_after

    def get_transactions(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        if not newest_first:
            return ProviderResult("ok", "etherscan", self.txs[-1:])
        if self.fail_after is not None and page > self.fail_after:
            return ProviderResult("unavailable", "etherscan", None, "http_500")
        return ProviderResult("ok", "etherscan", self.txs[(page - 1) * page_size : page * page_size])

    def get_token_transfers(self, chain_id, address, *, page=1, page_size=100, newest_first=True, end_block=None):
        return ProviderResult("ok", "etherscan", [])


class FakeRpc:
    def __init__(self, code="0x"):
        self.code = code

    def get_code(self, chain_id, address):
        return ProviderResult("ok", "alchemy", self.code)


class Unused:
    def __getattr__(self, name):
        raise AssertionError(f"{name} should not be called for a plain account")


class FakeGoPlus:
    def __init__(self, result):
        self.result = result

    def address_security(self, chain_id, address):
        return self.result

    def token_security(self, chain_id, address):
        raise AssertionError("token_security should not be called for a plain account")


def gp_ok(**flags):
    return ProviderResult(
        "ok", "goplus", SimpleNamespace(flags={"phishing_activities": False, **flags}, malicious_contracts_created=0)
    )


def run(*, txs=(), fail_after=None, code="0x", gp=None, lookup=None, intel_error=False):
    def intel(chain_id, addresses):
        if intel_error:
            raise RuntimeError("database down")
        return lookup if lookup is not None else IntelLookup({}, SOURCES)

    return analyze_wallet(
        1,
        SUBJECT,
        history_provider=FakeHistory(txs, fail_after),
        rpc=FakeRpc(code),
        explorer=Unused(),
        goplus=FakeGoPlus(gp or gp_ok()),
        intel_lookup=intel,
        now=NOW,
    )


def ids(report):
    return {e["id"] for e in report["evidence"]}


def cov(report, check):
    return next(c for c in report["coverage"] if c["check"] == check)


def test_clean_wallet_with_every_required_check_is_low_but_never_called_safe(monkeypatch):
    monkeypatch.setattr("app.engines.wallet.score_wallet", lambda h, n: ({"status": "not_trained", "version": None}, []))
    r = run()
    assert r["risk_level"] == "LOW"
    assert "not a guarantee" in r["summary"]
    assert r["model"] == {"status": "not_trained", "version": None}
    assert r["limitations"] and "does not mean an address is safe" in r["limitations"][0]


def test_report_has_the_spec_shape_and_hides_the_required_flag():
    r = run()
    assert set(r) == {
        "report_id", "chain_id", "subject", "risk_level", "summary", "evidence", "coverage",
        "consequences", "limitations", "model", "data_sources", "generated_at", "engine_version",
    }
    assert all(set(c) == {"check", "status", "source", "detail"} for c in r["coverage"])
    assert r["subject"] == {"type": "wallet", "key": SUBJECT}


def test_sanctioned_address_is_critical_even_when_goplus_is_down():
    lookup = IntelLookup({SUBJECT: (OFAC,)}, SOURCES)
    r = run(lookup=lookup, gp=ProviderResult("unavailable", "goplus", None, "http_500"))
    assert r["risk_level"] == "CRITICAL"
    assert "intel.ofac_sdn.sanctions.subject" in ids(r)
    assert cov(r, "goplus_address")["status"] == "unavailable"
    assert any("sanctioned" in c for c in r["consequences"])


def test_scam_list_hit_is_high():
    r = run(lookup=IntelLookup({SUBJECT: (SCAM,)}, SOURCES))
    assert r["risk_level"] == "HIGH"


def test_goplus_flag_alone_is_moderate_and_not_verified():
    r = run(gp=gp_ok(phishing_activities=True))
    assert r["risk_level"] == "MODERATE"
    flag = next(e for e in r["evidence"] if e["id"] == "provider.goplus.flags")
    assert flag["verified"] is False and "phishing_activities" in flag["claim"]


def test_goplus_unavailable_without_findings_is_insufficient_data():
    r = run(gp=ProviderResult("unavailable", "goplus", None, "http_500"))
    assert r["risk_level"] == "INSUFFICIENT_DATA"


def test_a_list_that_was_never_loaded_is_not_a_clean_result():
    only_ofac = IntelLookup({}, (IntelSourceInfo("ofac_sdn", "v", NOW), IntelSourceInfo("scamsniffer", None, None)))
    r = run(lookup=only_ofac)
    assert r["risk_level"] == "INSUFFICIENT_DATA"
    assert cov(r, "intel_lists") == {
        "check": "intel_lists", "status": "partial", "source": "chainguard_db", "detail": "list_not_loaded:scamsniffer",
    }


def test_database_failure_is_unavailable_not_clean():
    r = run(intel_error=True)
    assert r["risk_level"] == "INSUFFICIENT_DATA"
    assert cov(r, "intel_lists")["status"] == "unavailable"


def test_sanctioned_counterparty_is_high_and_names_the_source():
    lookup = IntelLookup({OTHER: (OFAC,)}, SOURCES)
    r = run(txs=[tx(1)], lookup=lookup)
    assert r["risk_level"] == "HIGH"
    e = next(e for e in r["evidence"] if e["id"] == "intel.ofac_sdn.counterparties")
    assert e["data"]["count"] == 1 and e["data"]["sample"] == [OTHER]


def test_eip7702_delegation_blocks_low():
    r = run(code="0xef0100" + "c" * 40)
    assert r["risk_level"] == "MODERATE"
    assert "code.eip7702" in ids(r)


def test_interrupted_history_is_partial_and_blocks_low():
    r = run(txs=[tx(i) for i in range(1000)], fail_after=1)
    assert cov(r, "transactions")["status"] == "partial"
    assert r["risk_level"] == "INSUFFICIENT_DATA"
    assert any("transactions" in line and "partly" in line for line in r["limitations"])


def test_age_comes_from_the_first_transaction_when_known():
    r = run(txs=[tx(5)])
    assert "wallet.age" in ids(r)
