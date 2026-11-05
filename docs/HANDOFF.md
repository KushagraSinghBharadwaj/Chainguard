# ChainGuard Handoff

## Status
- Phase 1: COMPLETE once these docs are committed (architecture, providers/datasets, schema, API contract, standards).
- Phase 2: Task 2.1 (backend foundation) done. Remaining: PostgreSQL install, models/migrations, auth, providers, endpoints.
- Phases 3-4: not started.

## Commits
- 6c9746e scaffold; ceb3fd7 FastAPI foundation (2 tests passing).

## Key decisions
D1-D7 in docs/ARCHITECTURE.md; P1-P4 in docs/PROVIDERS_AND_DATASETS.md; T1 (test fixtures) pending approval in docs/STANDARDS.md.

## Verified environment
Windows 11 Home; Git 2.54.0; Python 3.13.0; Node v22.18.0 / npm 10.9.3; Ryzen 7 5700U, 15.3 GB RAM, 191.8 GB free; AMD Radeon integrated GPU only.
PostgreSQL NOT installed. Chrome version unverified. Ollama deferred to the very end (do not install earlier).

## Phase 2 prerequisites (user)
- Free Etherscan API key (do not paste); report the limits shown on the account dashboard.
- RPC account choice: Alchemy or Infura (limits to be researched before wiring).

## Known issues
- Starlette/httpx deprecation warning in the test client (harmless; revisit).
- Etherscan free-tier limits CONFLICTING across sources; throttle to 3 req/s until verified.
- ScamSniffer address-list license unconfirmed.
- /health live response not yet viewed by the user.

## Next task
2.2 Install PostgreSQL, create `chainguard` database and role, connect from the backend.

## Resume prompt
"Continue ChainGuard. Read docs/HANDOFF.md, ARCHITECTURE.md, PROVIDERS_AND_DATASETS.md, DATABASE_SCHEMA.md,
API_SPEC.md and STANDARDS.md. One task at a time: explain, files, implement, verify, then wait for confirmation."
