# ChainGuard Architecture (approved, Task 1.1)

Components: Chrome extension (content script, injected EIP-1193 hook, background worker, popup)
-> FastAPI backend (API layer, orchestrator, wallet/token/transaction engines, evidence objects,
deterministic risk scorer, optional validated LLM explanations, deferred to the end of the project)
-> PostgreSQL, chain data providers (RPC + explorer APIs), intel sources, ML artifacts.

Design rules:
1. Evidence objects are the only input to the risk scorer.
2. Missing data is its own state; thin coverage = INSUFFICIENT DATA, never LOW.
3. ML is one evidence producer, not the judge. Shared feature module for training and inference.
4. The LLM only phrases findings; its output is validated against evidence.
5. Addresses are (chain_id, address) pairs; Ethereum mainnet first.
6. No extra infrastructure (Redis, Celery) until measurements justify it.

Approved decisions:
D1 Tiered scanning: local detection; light intel lookup automatic; deep analysis on click.
D2 History in chrome.storage.local; backend cache keyed by (chain, address), no user identity.
D3 Per-install rotating tokens plus per-token rate limits; no shared secret in the extension.
D4 Pre-signing is fail-open: if analysis is unavailable, say so and let the request proceed.
D5 Ethereum mainnet only, chain-abstracted design.
D6 Local backend during development; hosted deployment documented in Phase 4.
D7 Ollama is deferred to the very end, after backend, ML and extension are built and tested.

Full diagram: ChainGuard_Task1.1_Architecture.pdf