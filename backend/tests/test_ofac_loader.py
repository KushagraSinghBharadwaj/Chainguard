from datetime import date

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import IntelEntry, IntelSource
from app.db.session import get_engine
from app.intel.ofac import OfacEntry, OfacParseResult
from app.intel.ofac_loader import download_sdn, load_ofac, run_ofac_refresh

# FIXTURES: synthetic HTTP responses and XML, used only to test download/failure handling
# deterministically. The real file is covered by tests/test_ofac_live.py and the real refresh run.

XML = b'<?xml version="1.0" encoding="UTF-8"?><Sanctions></Sanctions>'


def addr(ch):
    return "0x" + ch * 40


SDN_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Sanctions xmlns="urn:test"><DateOfIssue><Year>2026</Year><Month>11</Month><Day>4</Day></DateOfIssue>'
    '<ReferenceValueSets><FeatureTypeValues><FeatureType ID="345">Digital Currency Address - ETH</FeatureType>'
    '</FeatureTypeValues></ReferenceValueSets><DistinctParties><DistinctParty><Profile>'
    '<Identity ID="1"><Alias Primary="true"><DocumentedName><DocumentedNamePart><NamePartValue>ACME</NamePartValue>'
    '</DocumentedNamePart></DocumentedName></Alias></Identity>'
    '<Feature ID="9" FeatureTypeID="345"><FeatureVersion ID="9"><VersionDetail DetailTypeID="1432">'
    + addr("a")
    + '</VersionDetail></FeatureVersion><IdentityReference IdentityID="1" /></Feature>'
    '</Profile></DistinctParty></DistinctParties></Sanctions>'
).encode()


def client_for(*steps):
    state = {"calls": 0}

    def handler(request):
        i = min(state["calls"], len(steps) - 1)
        state["calls"] += 1
        step = steps[i]
        if isinstance(step, Exception):
            raise step
        return step

    return httpx.Client(transport=httpx.MockTransport(handler)), state


def parsed(*entries):
    return OfacParseResult(tuple(entries), date(2026, 11, 4), len(entries), 0, {})


def test_download_writes_file(tmp_path):
    c, _ = client_for(httpx.Response(200, content=XML))
    dest = tmp_path / "f.xml"
    r = download_sdn(dest, client=c, sleep=lambda s: None)
    assert r.status == "ok" and r.data == dest and dest.read_bytes() == XML


def test_html_page_is_rejected_and_no_file_is_left(tmp_path):
    c, _ = client_for(httpx.Response(200, content=b"<html>blocked</html>"))
    dest = tmp_path / "f.xml"
    r = download_sdn(dest, client=c, sleep=lambda s: None)
    assert r.status == "unavailable" and r.detail == "unexpected_content" and not dest.exists()


def test_http_500_is_retried_then_unavailable(tmp_path):
    c, state = client_for(httpx.Response(500))
    sleeps = []
    r = download_sdn(tmp_path / "f.xml", client=c, sleep=sleeps.append)
    assert r.status == "unavailable" and r.detail == "http_500"
    assert state["calls"] == 3 and sleeps == [1.0, 2.0]


def test_http_429_is_rate_limited(tmp_path):
    c, state = client_for(httpx.Response(429))
    r = download_sdn(tmp_path / "f.xml", client=c, sleep=lambda s: None)
    assert r.status == "rate_limited" and state["calls"] == 3


def test_oversized_download_is_rejected_and_no_file_is_left(tmp_path):
    c, _ = client_for(httpx.Response(200, content=XML))
    dest = tmp_path / "f.xml"
    r = download_sdn(dest, client=c, sleep=lambda s: None, max_bytes=10)
    assert r.status == "unavailable" and r.detail == "too_large" and not dest.exists()


def test_http_404_is_not_retried(tmp_path):
    c, state = client_for(httpx.Response(404))
    r = download_sdn(tmp_path / "f.xml", client=c, sleep=lambda s: None)
    assert r.detail == "http_404" and state["calls"] == 1


def test_network_error_reports_class_name_only(tmp_path):
    c, state = client_for(httpx.ConnectError("boom"))
    r = download_sdn(tmp_path / "f.xml", client=c, sleep=lambda s: None)
    assert r.status == "unavailable" and r.detail == "ConnectError" and state["calls"] == 3


@pytest.fixture
def engine():
    eng = get_engine()
    if eng is None:
        pytest.skip("database is not configured")
    try:
        eng.connect().close()
    except Exception:
        pytest.skip("database is not reachable")
    return eng


@pytest.fixture
def source_name(engine):
    name = "ofac_sdn_test"
    yield name
    with Session(engine) as s, s.begin():
        sid = s.scalar(select(IntelSource.id).where(IntelSource.name == name))
        if sid is not None:
            s.execute(delete(IntelEntry).where(IntelEntry.source_id == sid))
            s.execute(delete(IntelSource).where(IntelSource.id == sid))


def stored(engine, name):
    with Session(engine) as s:
        sid = s.scalar(select(IntelSource.id).where(IntelSource.name == name))
        if sid is None:
            return []
        return sorted(s.scalars(select(IntelEntry.address).where(IntelEntry.source_id == sid)).all())


def load(engine, name, *entries):
    with Session(engine) as s:
        return load_ofac(s, parsed(*entries), source_url="https://example.test/x", source_name=name)


def test_load_inserts_entries_and_records_source(engine, source_name):
    out = load(engine, source_name, OfacEntry(addr("a"), "ACME"), OfacEntry(addr("b"), None))
    assert out.status == "loaded" and out.inserted == 2 and out.removed == 0
    with Session(engine) as s:
        src = s.scalar(select(IntelSource).where(IntelSource.name == source_name))
        assert src.version_label == "2026-11-04" and src.last_fetched_at is not None
        rows = s.scalars(select(IntelEntry).where(IntelEntry.source_id == src.id)).all()
        got = {(r.address, r.chain_id, r.category, r.label) for r in rows}
    assert got == {(addr("a"), 1, "sanctions", "ACME"), (addr("b"), 1, "sanctions", None)}


def test_reload_replaces_rows_and_reports_removed(engine, source_name):
    load(engine, source_name, OfacEntry(addr("a"), None), OfacEntry(addr("b"), None))
    out = load(engine, source_name, OfacEntry(addr("c"), None), OfacEntry(addr("d"), None))
    assert out.status == "loaded" and out.inserted == 2 and out.removed == 2
    assert stored(engine, source_name) == [addr("c"), addr("d")]


def test_empty_parse_is_refused_and_keeps_existing_rows(engine, source_name):
    load(engine, source_name, OfacEntry(addr("a"), None), OfacEntry(addr("b"), None))
    out = load(engine, source_name)
    assert out.status == "refused" and out.detail == "no_entries_parsed"
    assert stored(engine, source_name) == [addr("a"), addr("b")]


def test_sharp_drop_is_refused_and_keeps_existing_rows(engine, source_name):
    load(engine, source_name, *[OfacEntry(addr(c), None) for c in "abcd"])
    out = load(engine, source_name, OfacEntry(addr("e"), None))
    assert out.status == "refused" and out.detail == "entry_count_dropped_sharply"
    assert stored(engine, source_name) == [addr(c) for c in "abcd"]


def test_failed_insert_rolls_back_and_keeps_old_rows(engine, source_name):
    load(engine, source_name, OfacEntry(addr("a"), None), OfacEntry(addr("b"), None))
    with pytest.raises(IntegrityError):
        load(engine, source_name, OfacEntry(addr("c"), None), OfacEntry("0xZZ", None))
    assert stored(engine, source_name) == [addr("a"), addr("b")]


def test_run_refresh_reports_download_failure_and_touches_nothing(engine, source_name):
    c, _ = client_for(httpx.Response(500))
    out = run_ofac_refresh(engine, url="https://example.test/sdn", client=c, sleep=lambda s: None, source_name=source_name)
    assert out.status == "failed" and "http_500" in out.detail
    assert stored(engine, source_name) == []


def test_run_refresh_end_to_end_with_synthetic_file(engine, source_name):
    c, _ = client_for(httpx.Response(200, content=SDN_XML))
    out = run_ofac_refresh(engine, url="https://example.test/sdn", client=c, sleep=lambda s: None, source_name=source_name)
    assert out.status == "loaded" and out.inserted == 1 and out.published == date(2026, 11, 4)
    assert stored(engine, source_name) == [addr("a")]
