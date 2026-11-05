"""Training store tests. All data is SYNTHETIC: fake addresses."""

import pytest

from app.services import training_store as ts

A = "0x" + "a" * 40
B = "0x" + "B" * 40


@pytest.fixture
def conn():
    c = ts.connect(":memory:")
    yield c
    c.close()


def test_add_is_idempotent_and_lowercases(conn):
    assert ts.add_addresses(conn, 1, [A, B], "positive", "ofac_sdn") == 2
    assert ts.add_addresses(conn, 1, [A, B], "positive", "ofac_sdn") == 0
    assert {r["address"] for r in ts.claim_pending(conn, 10)} == {A, B.lower()}


def test_existing_label_is_never_overwritten(conn):
    ts.add_addresses(conn, 1, [A], "positive", "ofac_sdn")
    ts.add_addresses(conn, 1, [A], "unlabeled", "sampled")
    row = ts.claim_pending(conn, 1)[0]
    assert row["label"] == "positive" and row["source"] == "ofac_sdn"


def test_bad_label_is_rejected(conn):
    with pytest.raises(ValueError):
        ts.add_addresses(conn, 1, [A], "fraud", "x")


def test_done_rows_are_not_claimed_again(conn):
    ts.add_addresses(conn, 1, [A, B], "unlabeled", "sampled")
    ts.mark_done(conn, 1, A, 100, "2026-11-05T00:00:00+00:00", "[]")
    assert [r["address"] for r in ts.claim_pending(conn, 10)] == [B.lower()]


def test_failures_retry_then_stop(conn):
    ts.add_addresses(conn, 1, [A], "unlabeled", "sampled")
    for _ in range(ts.MAX_ATTEMPTS - 1):
        ts.mark_failed(conn, 1, A)
        assert len(ts.claim_pending(conn, 10)) == 1
    ts.mark_failed(conn, 1, A)
    assert ts.claim_pending(conn, 10) == []
    assert ts.counts(conn) == {"unlabeled:failed": 1}


def test_reopening_a_file_resumes(tmp_path):
    path = tmp_path / "t.sqlite"
    c = ts.connect(path)
    ts.add_addresses(c, 1, [A, B], "unlabeled", "sampled")
    ts.mark_done(c, 1, A, 1, "t", "[]")
    c.close()
    c2 = ts.connect(path)
    assert [r["address"] for r in ts.claim_pending(c2, 10)] == [B.lower()]
    c2.close()
