from app.engines.token_privileges import analyze_privileges


def fn(name):
    return {"type": "function", "name": name}


def cats(findings):
    return {f["category"] for f in findings}


def test_mint_owner():
    f = analyze_privileges([fn("mint"), fn("owner")])
    assert "mint" in cats(f)


def test_pause_blacklist_upgrade():
    f = analyze_privileges([fn("pause"), fn("addBlackList"), fn("upgradeTo")])
    assert {"pause", "blacklist", "upgrade"} <= cats(f)


def test_plain_token():
    f = analyze_privileges([fn("transfer"), fn("balanceOf")])
    assert cats(f) == {"owner_getter"}


def test_empty_abi():
    assert analyze_privileges(None) == []