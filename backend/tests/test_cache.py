import pytest

from app.providers.cache import (
    NOT_FOUND_TTL_SECONDS,
    build_cache_key,
    make_envelope,
    read_envelope,
    ttl_for,
)

A = "0x" + "a" * 40


def test_key_is_stable_and_order_independent():
    k1 = build_cache_key("etherscan", 1, "contract_source", {"address": A, "page": 1})
    k2 = build_cache_key("etherscan", 1, "contract_source", {"page": 1, "address": A})
    assert k1 == k2


def test_key_ignores_address_case():
    k1 = build_cache_key("etherscan", 1, "contract_source", {"address": A})
    k2 = build_cache_key("etherscan", 1, "contract_source", {"address": A.upper().replace("0X", "0x")})
    assert k1 == k2


def test_key_differs_by_chain_operation_and_params():
    base = build_cache_key("etherscan", 1, "contract_source", {"address": A})
    assert base != build_cache_key("etherscan", 10, "contract_source", {"address": A})
    assert base != build_cache_key("etherscan", 1, "wallet_page", {"address": A})
    assert base != build_cache_key("etherscan", 1, "contract_source", {"address": "0x" + "b" * 40})


@pytest.mark.parametrize("name", ["apikey", "api_key", "key", "token", "secret", "Authorization"])
def test_secret_like_params_are_refused(name):
    with pytest.raises(ValueError):
        build_cache_key("etherscan", 1, "contract_source", {"address": A, name: "SECRET-VALUE"})


def test_key_contains_no_param_values():
    k = build_cache_key("etherscan", 1, "contract_source", {"address": A})
    assert A not in k and k.startswith("etherscan:1:contract_source:")


@pytest.mark.parametrize("status", ["unavailable", "rate_limited", "error", "skipped"])
def test_failures_are_never_enveloped(status):
    with pytest.raises(ValueError):
        make_envelope(status, {"x": 1})


def test_ok_envelope_roundtrip_and_empty_list_is_a_real_answer():
    assert read_envelope(make_envelope("ok", {"a": 1})) == (True, {"a": 1})
    assert read_envelope(make_envelope("ok", [])) == (True, [])


def test_ok_without_raw_is_refused():
    with pytest.raises(ValueError):
        make_envelope("ok", None)


def test_not_found_envelope_has_no_raw():
    env = make_envelope("not_found", None)
    assert "raw" not in env and read_envelope(env) == (False, None)


@pytest.mark.parametrize("bad", [None, [], {}, {"v": 2, "found": True, "raw": 1}, {"v": 1, "found": True}, {"v": 1}])
def test_invalid_rows_are_ignored(bad):
    assert read_envelope(bad) is None


def test_ttls():
    assert ttl_for("contract_source") == 86_400
    assert ttl_for("contract_source", found=False) == NOT_FOUND_TTL_SECONDS
    with pytest.raises(ValueError):
        ttl_for("made_up_operation")
