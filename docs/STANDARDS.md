# ChainGuard Engineering, Testing, Security and Logging Standards

## Code structure
- Dependency direction: api -> services -> engines/providers. Engines never import the api layer.
- One module normalizes and validates addresses; nothing else parses address strings.
- Provider adapters implement one interface per capability so a provider can be replaced without engine changes.
- Type hints on all functions; Pydantic for every external boundary; UTC timestamps only.
- Failures are explicit typed results (`unavailable`, `rate_limited`, `not_found`), never empty lists or defaults.

## Testing
- pytest for backend. Layers: unit (pure logic), integration (API + database), live (real providers).
- DECISION T1 (needs your approval): the project rule forbids mock data in the PRODUCT. Tests are different: to test
  429/timeout handling and parsing deterministically we need recorded or synthetic responses. Proposal: such test
  fixtures live only under `backend/tests/`, are labeled as fixtures, and are never importable by product code.
  Real-provider behavior is verified by `@pytest.mark.live` tests that run with real keys and are not run by default.
- Every bug fix gets a regression test. The known httpx deprecation warning is tracked and revisited.

## Security
- Secrets only in `backend/.env` (git-ignored) or environment variables; never in extension code or Git.
- Settings use SecretStr; no endpoint returns a secret value.
- Authentication on all `/v1` routes except registration; tokens hashed at rest; per-token and per-IP rate limits.
- No CORS middleware until required; the extension background worker calls the API with host permissions.
- Input validation on every field; size limits; reject unknown fields.
- Dependencies are pinned in a lock file and reviewed when updated.
- The system never requests, stores or logs private keys, seed phrases or signatures, and never signs anything.

## Logging
- Structured JSON to stdout. Log request_id, method, route path, status, duration.
- Do NOT log query strings, request bodies, addresses, calldata, tokens or provider keys.
- Provider failures are logged with provider name and error class only.

## Git
- Branch `main`; conventional commit messages (feat, fix, docs, chore, test); one logical change per commit.
- `.env` files are never committed (enforced by .gitignore; verified before each commit).

## Phase 1 exit criteria
Architecture approved; providers/intel/dataset strategy approved; schema, API contract and standards written;
environment recorded; repo scaffolded and committed. Items needing user accounts (Etherscan key, RPC account)
are Phase 2 prerequisites.

## Rate limiting
- Authenticated /v1 routes: per-IP bucket (before DB lookup) and per-token bucket (after auth); 429 with Retry-After. Registration has its own per-IP bucket.
- Limits are configurable via RATE_LIMIT_* settings. X-Forwarded-For is ignored unless TRUST_PROXY_HEADERS=true (spoofable otherwise).
- Known limitation: buckets are in-process memory. With multiple workers each has its own counters, so effective limits multiply. Move to a shared store (e.g. Redis or PostgreSQL) before multi-worker deployment.

