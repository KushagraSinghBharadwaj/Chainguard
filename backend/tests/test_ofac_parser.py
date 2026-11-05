import io

from app.intel.ofac import parse_sdn_advanced

# FIXTURE: synthetic XML modelled on the structure of OFAC's SDN_ADVANCED.XML, used only to
# test parsing and failure accounting deterministically. Real data is covered by test_ofac_live.py.

A1 = "0x" + "a" * 40
A2 = "0x" + "b" * 40
A3 = "0x" + "c" * 40
VALID_CHECKSUM = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
BAD_CHECKSUM = "0x5AAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"


def feature(fid, type_id, value, identity):
    ref = f'<IdentityReference IdentityID="{identity}" />' if identity else ""
    return (
        f'<Feature ID="{fid}" FeatureTypeID="{type_id}"><FeatureVersion ID="{fid}">'
        f'<VersionDetail DetailTypeID="1432">{value}</VersionDetail></FeatureVersion>{ref}</Feature>'
    )


def identity(iid, *names):
    parts = "".join(f"<DocumentedNamePart><NamePartValue>{n}</NamePartValue></DocumentedNamePart>" for n in names)
    return f'<Identity ID="{iid}"><Alias Primary="true"><DocumentedName>{parts}</DocumentedName></Alias></Identity>'


def build(*features, identities=None, date_xml=True):
    ids = identities if identities is not None else identity(1, "ACME", "Corp") + identity(2, "Second Party")
    date = "<DateOfIssue><Year>2026</Year><Month>11</Month><Day>4</Day></DateOfIssue>" if date_xml else ""
    xml = (
        '<Sanctions xmlns="urn:test">' + date
        + '<ReferenceValueSets><FeatureTypeValues>'
        '<FeatureType ID="344">Digital Currency Address - XBT</FeatureType>'
        '<FeatureType ID="345">Digital Currency Address - ETH</FeatureType>'
        '<FeatureType ID="887">Digital Currency Address - USDT</FeatureType>'
        '<FeatureType ID="689">Digital Currency Address - ETC</FeatureType>'
        '</FeatureTypeValues></ReferenceValueSets>'
        "<DistinctParties><DistinctParty><Profile>" + ids + "".join(features)
        + "</Profile></DistinctParty></DistinctParties></Sanctions>"
    )
    return io.BytesIO(xml.encode("utf-8"))


def test_eth_addresses_are_extracted_lowercased_and_labeled():
    r = parse_sdn_advanced(build(feature(1, 345, VALID_CHECKSUM, 1), feature(2, 345, A1, 2)))
    by_addr = {e.address: e.label for e in r.entries}
    assert by_addr[VALID_CHECKSUM.lower()] == "ACME Corp"
    assert by_addr[A1] == "Second Party"
    assert r.eth_rows_seen == 2 and r.rejected == 0


def test_non_eth_0x_addresses_are_counted_not_loaded():
    r = parse_sdn_advanced(build(feature(1, 345, A1, 1), feature(2, 887, A2, 1), feature(3, 689, A3, 1)))
    assert [e.address for e in r.entries] == [A1]
    assert r.other_0x_rows == {"USDT": 1, "ETC": 1}


def test_duplicate_address_is_merged_and_labels_are_combined():
    r = parse_sdn_advanced(build(feature(1, 345, A1, 1), feature(2, 345, A1.upper().replace("0X", "0x"), 2)))
    assert len(r.entries) == 1 and r.eth_rows_seen == 2
    assert r.entries[0].label == "ACME Corp; Second Party"


def test_invalid_checksum_is_counted_as_rejected_not_silently_dropped():
    r = parse_sdn_advanced(build(feature(1, 345, A1, 1), feature(2, 345, BAD_CHECKSUM, 1)))
    assert [e.address for e in r.entries] == [A1]
    assert r.eth_rows_seen == 2 and r.rejected == 1


def test_bitcoin_style_values_are_ignored():
    r = parse_sdn_advanced(build(feature(1, 344, "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", 1), feature(2, 345, A1, 1)))
    assert [e.address for e in r.entries] == [A1] and r.other_0x_rows == {}


def test_missing_identity_gives_no_label_and_date_is_parsed():
    r = parse_sdn_advanced(build(feature(1, 345, A1, None)))
    assert r.entries[0].label is None
    assert r.published is not None and r.published.isoformat() == "2026-11-04"
