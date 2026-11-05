import os
from pathlib import Path

import pytest

from app.intel.ofac import parse_sdn_advanced

pytestmark = pytest.mark.live

PATH = Path(os.environ.get("TEMP", ".")) / "ofac" / "sdn_advanced.xml"


def test_live_parse_of_real_sdn_file():
    if not PATH.exists():
        pytest.skip(f"download the real file to {PATH} first")
    r = parse_sdn_advanced(PATH)
    print("\nOFAC: published", r.published)
    print("OFAC: eth rows seen", r.eth_rows_seen, "unique entries", len(r.entries), "rejected", r.rejected)
    print("OFAC: other 0x rows (not loaded)", r.other_0x_rows)
    for e in r.entries[:3]:
        print("OFAC: sample", e.address, "|", e.label)
    print("OFAC: entries without a label", sum(1 for e in r.entries if e.label is None))
    assert r.published is not None
    assert 50 <= len(r.entries) <= 1000
    assert r.rejected == 0
    assert all(len(e.address) == 42 and e.address == e.address.lower() for e in r.entries)
