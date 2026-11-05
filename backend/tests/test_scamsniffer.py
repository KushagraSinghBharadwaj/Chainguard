import json

import pytest
from sqlalchemy import text

from app.db.session import get_engine
from app.intel.scamsniffer import parse_scamsniffer
from app.intel.scamsniffer_loader import load_entries

from datetime import datetime, timezone

CHECKSUMMED = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"  # EIP-55 specification example
BAD_CHECKSUM = "0x5aaeb6053F3E94C9b9A09f33669435E7Ef1BeAed"  # same address, one letter's case flipped
TEST_SOURCE = "scamsniffer_test"


def _raw(addresses):
    return json.dumps({"address": addresses, "domains": [], "combined": []})


def test_lowercases_and_dedupes():
    r = parse_scamsniffer(_raw([CHECKSUMMED, CHECKSUMMED.lower()]))
    assert r.addresses == (CHECKSUMMED.lower(),)
    assert r.duplicates == 1 and r.rows_seen == 2


def test_non_evm_entries_are_counted_not_dropped():
    r = parse_scamsniffer(_raw(["0x" + "11" * 20, "0x1234", "9" * 44, 123]))
    assert len(r.addresses) == 1
    assert r.non_evm == 3
    assert len(r.rejected_samples) == 3


def test_bad_checksum_is_counted_invalid():
    r = parse_scamsniffer(_raw([BAD_CHECKSUM]))
    assert r.addresses == () and r.invalid == 1


def test_missing_address_key_raises():
    with pytest.raises(ValueError):
        parse_scamsniffer(json.dumps({"domains": []}))


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_scamsniffer("not json")


def _cleanup():
    with get_engine().begin() as conn:
        p = {"n": TEST_SOURCE}
        conn.execute(text("DELETE FROM intel_entries WHERE source_id IN (SELECT id FROM intel_sources WHERE name = :n)"), p)
        conn.execute(text("DELETE FROM intel_sources WHERE name = :n"), p)


@pytest.fixture
def clean_source():
    _cleanup()
    yield
    _cleanup()


def _count():
    with get_engine().connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM intel_entries e JOIN intel_sources s ON s.id = e.source_id WHERE s.name = :n"),
            {"n": TEST_SOURCE},
        ).scalar_one()


def _load(addresses):
    return load_entries(
        get_engine(),
        parse_scamsniffer(_raw(addresses)),
        license_note="test",
        version_label="test",
        fetched_at=datetime.now(timezone.utc),
        source_name=TEST_SOURCE,
    )


def test_refuses_empty_list(clean_source):
    with pytest.raises(ValueError):
        _load([])
    assert _count() == 0


def test_load_replaces_rows_and_stores_null_chain(clean_source):
    assert _load(["0x" + "11" * 20, "0x" + "22" * 20]) == 2
    assert _load(["0x" + "33" * 20, "0x" + "44" * 20, "0x" + "55" * 20]) == 3
    assert _count() == 3
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT e.chain_id, e.category FROM intel_entries e JOIN intel_sources s ON s.id = e.source_id WHERE s.name = :n LIMIT 1"),
            {"n": TEST_SOURCE},
        ).one()
    assert row[0] is None and row[1] == "phishing"


def test_shrink_guard_rolls_back(clean_source):
    _load(["0x" + f"{i:02x}" * 20 for i in range(1, 5)])
    with pytest.raises(ValueError):
        _load(["0x" + "99" * 20])
    assert _count() == 4
