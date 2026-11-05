# External API and data dependencies

Status legend: VERIFIED = exercised against the real service (live tests). UNVERIFIED = assumed, not yet observed.

## Etherscan V2 (provider adapter: backend/app/providers/etherscan.py)
- Purpose: wallet transaction history and contract metadata.
- Auth: API key, ETHERSCAN_API_KEY in backend/.env. Never logged (regression test: tests/test_no_key_in_logs.py).
- Behaviour: throttled, bounded retries, typed results (ok / not_found / rate_limited / unavailable). VERIFIED live.
- Limits: see the adapter's throttle setting and the Etherscan plan page. Not restated here.

## Alchemy JSON-RPC (backend/app/providers/alchemy.py)
- Purpose: eth_getCode, eth_call (with revert detection), eth_getStorageAt on Ethereum mainnet.
- Auth: API key inside the request URL path, ALCHEMY_API_KEY in backend/.env. httpx logging is raised to WARNING so the URL is never logged.
- VERIFIED live (tests/test_alchemy_live.py), including: reverts are reported as a revert outcome, EIP-7702 delegated wallets return 0xef0100... code, USDC stores its implementation in the legacy zos slot (not the EIP-1967 slot).

## GoPlus Security API (backend/app/providers/goplus.py)
- Purpose: token security fields and address risk flags.
- Endpoints used: GET /api/v1/token_security/{chain_id}, GET /api/v1/address_security/{address}.
- Auth: none (keyless). Rate limits for the keyless tier are UNVERIFIED: no rate-limit headers were observed. Throttle default is 1 request per second.
- Observed behaviour, recorded as fixtures in backend/tests/fixtures/goplus_*.json:
  - Errors are returned with HTTP 200 and a non-1 code (2022 unsupported chain, 5000 system error for a malformed address).
  - An unknown token returns HTTP 200, code 1 and an empty result: mapped to not_found, never to safe.
  - Booleans are the strings 0 and 1. Fields can be absent: absent means not provided.
  - GoPlus lists ScamSniffer and SlowMist among its own data sources, so its flags are not independent of our ScamSniffer table.
  - It did not set sanctioned for an address that OFAC lists. Report each source separately.
- A real rate-limit response has not been observed: detection by message text is UNVERIFIED.

## OFAC SDN list (backend/app/intel/ofac.py, ofac_loader.py)
- Purpose: sanctions attribution for Ethereum addresses (123 loaded).
- Source: US Treasury OFAC Sanctions List Service (SDN Advanced XML).
- License note stored in intel_sources.license_note: data.gov catalog record marks the SDN list as public with a CC0 licence; underlying content is a US federal work. Provenance is data.gov metadata, not an OFAC licence page.
- Not a complete picture of sanctions risk: only addresses OFAC publishes.

## ScamSniffer scam-database (backend/app/intel/scamsniffer.py, scamsniffer_loader.py)
- Purpose: phishing and drainer addresses (4,599 loaded, chain_id NULL meaning EVM-wide).
- Source: https://github.com/scamsniffer/scam-database, blacklist/all.json.
- License: GNU GPL v3, verified by the loader reading the repository LICENSE file at load time. Server-side use only: the list is never bundled into the extension or redistributed. Unreviewed by a lawyer.
- Freshness: the upstream list is published with a 7-day delay, so it cannot contain the newest phishing addresses. Reports must say so.
- Data quality: 8 of 4,607 upstream entries were malformed (stray characters, truncated, "null", "0x0") and are rejected and counted, never repaired.
