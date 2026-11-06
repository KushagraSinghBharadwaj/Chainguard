"""Detect privileged functions from a verified ABI. Facts only, no scores."""

PRIVILEGE_PATTERNS = {
    "mint": ("mint", "issue"),
    "pause": ("pause", "unpause"),
    "blacklist": ("blacklist", "addblacklist", "blocklist", "addtoblacklist",
                  "removeblacklist", "destroyblackfunds"),
    "upgrade": ("upgradeto", "upgradetoandcall", "setimplementation"),
    "ownership": ("transferownership", "renounceownership"),
    "fees": ("setfee", "settax", "setfees", "settaxfee"),
}


def _fn_names(abi):
    return [
        item["name"]
        for item in (abi or [])
        if item.get("type") == "function" and item.get("name")
    ]


def analyze_privileges(abi):
    """Return a list of findings: {category, functions, note}."""
    if not abi:
        return []
    names = _fn_names(abi)
    findings = []
    for category, patterns in PRIVILEGE_PATTERNS.items():
        hits = sorted(
            n for n in names if any(n.lower() == p or n.lower().startswith(p) for p in patterns)
        )
        if hits:
            findings.append({
                "category": category,
                "functions": hits,
                "note": f"Contract exposes {category} functions. "
                        "Presence is a fact, not proof of misuse.",
            })
    has_owner = any(n == "owner" for n in names)
    findings.append({
        "category": "owner_getter",
        "functions": ["owner"] if has_owner else [],
        "note": "owner() present; renounced status needs an on-chain call."
                if has_owner else "No owner() function in ABI.",
    })
    return findings