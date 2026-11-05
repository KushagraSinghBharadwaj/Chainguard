import pytest

from app.intel.scamsniffer_loader import DATA_URL, _download
from app.intel.scamsniffer import parse_scamsniffer

pytestmark = pytest.mark.live


def test_live_real_file_parses_and_counts_add_up():
    r = parse_scamsniffer(_download(DATA_URL))
    print("\nrows:", r.rows_seen, "valid:", len(r.addresses), "non_evm:", r.non_evm,
          "invalid:", r.invalid, "dupes:", r.duplicates, "samples:", list(r.rejected_samples))
    assert len(r.addresses) > 1000
    assert r.rows_seen == len(r.addresses) + r.non_evm + r.invalid + r.duplicates
