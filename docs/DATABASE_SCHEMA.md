# ChainGuard Database Schema (Phase 1 design; implemented with SQLAlchemy + Alembic in Phase 2)

Database: PostgreSQL, dedicated database `chainguard` with its own role (never shared with other projects).
Conventions: UTC timestamptz everywhere; uuid primary keys for client-facing ids; addresses stored lowercase
(`0x` + 40 hex, CHECK constraint) and converted to EIP-55 checksum only for display.

Privacy (decision D2): no table stores a user identity, IP address or browsing history. Analysis history lives
in the extension's chrome.storage.local, not here.

## Enum: risk_level
LOW, MODERATE, HIGH, CRITICAL, INSUFFICIENT_DATA

## Tables (Phase 2 migration 0001)

### chains
| column | type | notes |
|---|---|---|
| chain_id | integer PK | 1 = Ethereum mainnet |
| name | text not null | |
| native_symbol | text not null | ETH |
| enabled | boolean not null default false | only chain 1 enabled at launch |

### clients  (one row per extension install)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| created_at | timestamptz not null | |
| last_seen_at | timestamptz | |
| revoked_at | timestamptz | null = active |

### client_tokens  (rotating bearer tokens; plaintext is never stored)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| client_id | uuid FK clients | |
| token_hash | text unique not null | SHA-256 of the token |
| issued_at / expires_at | timestamptz not null | |
| revoked_at | timestamptz | |

### provider_cache  (raw public chain/provider responses, to protect rate limits)
| column | type | notes |
|---|---|---|
| cache_key | text PK | e.g. `etherscan:txlist:1:<addr>:p1` |
| provider | text not null | |
| payload | jsonb not null | |
| fetched_at | timestamptz not null | |
| expires_at | timestamptz not null | index; expired rows purged by a job |

Failed provider calls are NOT cached as empty results; failures are never stored as "no data".

### intel_sources
| column | type | notes |
|---|---|---|
| id | smallint PK | |
| name | text unique not null | ofac_sdn, scamsniffer, goplus |
| url | text | |
| license_note | text | recorded after the license is actually read |
| version_label | text | list date or commit hash |
| last_fetched_at | timestamptz | |

### intel_entries  (downloaded denylist data)
| column | type | notes |
|---|---|---|
| id | bigint PK | |
| source_id | smallint FK intel_sources | |
| chain_id | integer FK chains, nullable | null for domains or chain-agnostic entries |
| address | text, nullable | lowercase; null for domain entries |
| domain | text, nullable | |
| category | text not null | sanctions, phishing, drainer, ... |
| label | text | |
| fetched_at | timestamptz not null | |

UNIQUE (source_id, chain_id, address, domain, category); index on (chain_id, address). Each refresh replaces a
source's rows in one transaction, so entries removed upstream are removed here too.

### analysis_reports  (shared cache of completed reports, no user identity)
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| chain_id | integer FK chains | |
| subject_type | text | wallet, token, transaction |
| subject_key | text | address, or hash of the normalized transaction request |
| risk_level | risk_level not null | |
| report | jsonb not null | full report including evidence and coverage |
| engine_version | text not null | |
| model_version | text | null when no ML model was used |
| created_at / expires_at | timestamptz not null | |

Index (chain_id, subject_type, subject_key, created_at desc). Expired reports are recomputed, never extended.
Evidence objects live inside the report jsonb so a report is a self-contained, auditable record.

## Added in Phase 3 migrations
### model_registry
id, name, version, trained_at, dataset_ref, metrics (jsonb), artifact_sha256, status (candidate/active/retired).
A model can be set active only if its evaluation metrics are stored here.

## Rate limiting
Per-token and per-IP limits use an in-process token bucket for the single-process development setup. This is a
documented limitation: with multiple workers, limits would need a shared store (not introduced until needed).
