# ChainGuard

AI-powered cryptocurrency fraud detection Chrome extension (Manifest V3) with a FastAPI backend.

Status: Phase 1 (design and foundation). See docs/HANDOFF.md for current progress.

Capabilities (planned): wallet fraud detection, token/contract risk analysis, pre-signing transaction risk analysis.

Hard rules: never request or store private keys or seed phrases; never sign transactions; no fake data; unknown is never reported as safe.