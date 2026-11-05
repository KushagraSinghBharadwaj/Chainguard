# ChainGuard API Contract v1 (Phase 1 design)

Base path `/v1`. JSON only. All timestamps UTC ISO-8601. Implemented in Phase 2 (endpoints) and Phase 3 (engines).

## Authentication (decision D3)
- `POST /v1/clients/register` -> `{client_id, token, expires_at}`. Public, strictly rate limited per IP.
- `POST /v1/clients/token/refresh` (Bearer) -> new token; old token revoked.
- All other `/v1` routes require `Authorization: Bearer <token>`. Tokens are stored hashed.
- `GET /health` stays public. `/config/status` (currently unauthenticated) moves to `/v1/config/status` behind auth in Phase 2.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | /v1/addresses/lookup | Light check, auto-triggered by page scans (D1) |
| POST | /v1/wallets/analyze | Deep wallet analysis (Module 1) |
| POST | /v1/tokens/analyze | Token/contract analysis (Module 2) |
| POST | /v1/transactions/analyze | Pre-signing transaction analysis (Module 3) |

### POST /v1/addresses/lookup
Request: `{ "chain_id": 1, "addresses": ["0x..."] }` (max 25 addresses).
Response per address: `address_type` (`eoa` | `contract` | `unknown`), `intel_hits[]` (source, category, list version,
fetched_at), `status` (`checked` | `unavailable`). No deep analysis, no ML. "No hits" means "not found on these lists".

### POST /v1/wallets/analyze, /v1/tokens/analyze
Request: `{ "chain_id": 1, "address": "0x..." }` -> Report.

### POST /v1/transactions/analyze
Request:
```
{ "chain_id": 1, "from": "0x...", "to": "0x..." | null, "value_wei": "0",
  "data": "0x...", "typed_data": null | {...EIP-712 payload...} }
```
`data` max 100000 hex chars. The service only analyzes; it never signs and never holds keys.

## Report object (identical for all three modules)
```
{
  "report_id": "uuid",
  "chain_id": 1,
  "subject": { "type": "wallet|token|transaction", "key": "..." },
  "risk_level": "LOW|MODERATE|HIGH|CRITICAL|INSUFFICIENT_DATA",
  "summary": "deterministic text built from evidence",
  "evidence": [ Evidence ],
  "coverage": [ { "check": "...", "status": "completed|partial|unavailable|skipped",
                  "source": "...", "detail": "..." } ],
  "consequences": [ "plain-language possible outcomes" ],
  "limitations": [ "what was not checked or could not be known" ],
  "model": { "status": "used|unavailable", "version": null },
  "data_sources": [ { "name": "...", "fetched_at": "..." } ],
  "generated_at": "...", "engine_version": "..."
}
```
`partial` means the check ran but its data was truncated or interrupted; `detail` says what is missing.

Evidence: `{ id, kind: rule|ml|intel|provider, claim, severity: info|low|moderate|high|critical,
confidence: 0..1, verified: bool, data: {...}, source: {name, fetched_at} }`.

### Risk-level rules (principles; exact thresholds are specified and tested in Phase 3)
1. Only evidence objects influence the level. The LLM (deferred) never changes it.
2. A verified critical/high finding sets a floor for the level.
3. LOW is allowed only if every required check in `coverage` is `completed` (not `partial`) and produced no findings.
4. If required checks are `unavailable` or `partial`, the level is INSUFFICIENT_DATA (or higher if evidence already warrants it).
5. Every LOW report still lists limitations; nothing is called "safe".

## Errors
Envelope: `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`
401 unauthenticated, 422 validation, 429 rate limited (with `Retry-After`), 502 provider failure,
503 provider unavailable. A provider failure inside an analysis is NOT an HTTP error when a partial report is
possible: it appears as `coverage.status = unavailable`.

## Input validation
- `chain_id` must be an enabled chain (only 1 at launch).
- Addresses: `^0x[0-9a-fA-F]{40}$`; mixed-case input must pass the EIP-55 checksum; stored lowercase.
- Strict Pydantic models, unknown fields rejected, size limits on every list and hex field.

Response (added with Task 4.6): `{ "chain_id": 1, "results": [ { "address": "0x...", "address_type": "...", "intel_hits": [...], "status": "..." } ] }`.
Addresses are returned lowercase, deduplicated, in request order. `status` is `checked` only when both lists are loaded; otherwise `unavailable`, and "no hits" must not be read as clean. `eoa` includes EIP-7702 delegated accounts.
