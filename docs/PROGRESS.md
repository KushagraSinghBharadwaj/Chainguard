# ChainGuard Progress Log (updated 2026-11-05)

Repo: C:\Dev\chainguard (local git, branch main). Backend in backend\, docs in docs\.
Read order for a new Claude: docs/HANDOFF.md, this file, then the other docs.
Working style: one task at a time, numbered steps only, several steps per message. The user runs commands in Windows PowerShell and pastes the output. Never assume a command worked. Real data only, no mocks in product code.

## Done (commit - what)
- 6c9746e - scaffold and architecture docs
- 2be9dc8 - Phase 1 design docs (providers, schema, API contract, standards, handoff)
- ceb3fd7 - 2.1 FastAPI foundation: typed settings (SecretStr), JSON logging (no query strings), /health
- (no commit) 2.2a - PostgreSQL 18 installed (service postgresql-x64-18, port 5432), role and database chainguard, DATABASE_URL in backend\.env (git-ignored)
- d8c97a9 - 2.2b SQLAlchemy engine (app/db/session.py); /health reports database ok|unavailable|not_configured from a real SELECT 1
- 0454b9f - 2.3 Alembic plus models for 7 tables; migration 0001 seeds chain 1 (Ethereum Mainnet); downgrade drops the risk_level enum
- dbeb3a7 - 2.4 auth: POST /v1/clients/register and /v1/clients/token/refresh, SHA-256 hashed 30-day tokens, per-IP token bucket (5/min), error envelope with request_id
- bcc11af - 2.5 EIP-55 address module (app/core/addresses.py), strict Pydantic request schemas (app/schemas/requests.py), /config/status moved to /v1/config/status behind auth

Tests: 48 passing. Integration tests use the real local database and clean up their rows.

## Environment notes
- Windows 11, PowerShell, Python 3.13, venv at backend\.venv (activate with .\.venv\Scripts\Activate.ps1).
- PostgreSQL bin path C:\Program Files\PostgreSQL\18\bin must be added to PATH per PowerShell window.
- In PowerShell a backtick-n is a newline only inside double quotes. Edit files with .Replace() and write with Set-Content -Encoding ascii.
- Lock file: pip freeze | Set-Content requirements.lock.txt -Encoding ascii (inside the venv); the diff should only add lines.
- Alembic: alembic upgrade head; alembic check should report no new operations.

## Next
- 2.6 Etherscan provider adapter (typed results ok/rate_limited/unavailable/not_found, 3 req/s throttle, limited retries, provider_cache). Needs ETHERSCAN_API_KEY in backend\.env (the user adds it; never pasted in chat).
- Then RPC adapter (Alchemy or Infura), intel loaders (OFAC, ScamSniffer, GoPlus), per-token rate limiting.

## Open items
- Decision T1 (test fixtures only under backend/tests/) awaiting approval; recommended yes.
- Etherscan free-tier limits unverified (sources conflict); read the dashboard.
- ScamSniffer address license unconfirmed.
- httpx/Starlette TestClient deprecation warning (asks for httpx2).
- Phases 3-10 (engines, ML, extension) not started.
