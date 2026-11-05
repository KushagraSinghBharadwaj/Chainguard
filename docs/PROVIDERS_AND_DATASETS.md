# ChainGuard: Providers, Intelligence Sources and Dataset Strategy

Date: 2026-11-05 | Status: APPROVED (P1-P4 accepted 2026-11-05) | Covers Tasks 1.4, 1.5 and the ML strategy part of 1.8

Evidence standard: every claim below is marked VERIFIED (seen in a retrieved source), CONFLICTING (sources disagree), or UNVERIFIED (not yet checked). Nothing here has been tested against a live API. Limits and licenses change, so each must be re-checked on the vendor's own page before we depend on it.

## 1. Chain data providers

| Need | Proposed provider | What was found | Status |
|---|---|---|---|
| Wallet history, token transfers, verified contract source (getsourcecode) | Etherscan API V2 (primary) | Single key works across chains via a chainid parameter. Base URL api.etherscan.io/v2/api. Strong verified-contract coverage. Token-info endpoints need a paid plan. | VERIFIED |
| Etherscan free-tier limits | - | Several sources say 5 calls/sec and 100k/day. Blockscout's docs say 3 RPS and limited chains. Etherscan's own error docs describe a shared "Community Free API limit" pool that can run out for everyone. | CONFLICTING |
| Fallback explorer | Blockscout PRO API (Etherscan-compatible endpoints) | Vendor docs: free tier 100K credits/day, 5 RPS, key required. This is the vendor's own marketing claim. | VERIFIED (vendor claim) |
| Direct node access (eth_getCode, eth_call, simulation) | Alchemy or Infura free tier | Not researched yet. | UNVERIFIED |
| Function-selector decoding | 4byte / OpenChain signature database, Sourcify for verified ABIs | Not researched yet. | UNVERIFIED |

Design consequences:
- Throttle to 3 requests/sec until the real limit on our own key is confirmed in the Etherscan dashboard.
- Handle "Max rate limit reached" and "Community Free API limit reached" as an explicit PROVIDER_UNAVAILABLE evidence state, never as an empty result.
- Provider adapters share one interface so Blockscout can replace Etherscan without engine changes.

## 2. Fraud intelligence sources

| Source | Use | What was found | Status |
|---|---|---|---|
| OFAC SDN list (US Treasury) | Sanctioned addresses (deterministic rule, high confidence) | Published by the US Treasury, includes digital currency addresses. Direct page not fetched in this research. | UNVERIFIED (details) |
| ScamSniffer scam-database (GitHub) | Phishing and drainer addresses and domains | Daily updates with a 7-day delay. A real-time API costs from $999/month. A third party reports the repository is GPL-3.0; the repo page itself showed no license text. The ScamSniffer site says the domain list is free for commercial use but does not say the same for addresses. | CONFLICTING (license) |
| GoPlus Security API | Token security (honeypot, taxes, owner powers), malicious address, approval security, signature decoding, transaction simulation | Free tier published at 150K CU/month, 30K CU/day, 150 CU/min. No bulk download. Third-party service, so its output is evidence with source "goplus", not ground truth. | VERIFIED (published limits), terms UNVERIFIED |
| Etherscan labels | Exchange and entity attribution | Label access beyond the basic API is not confirmed free. | UNVERIFIED |

Rules:
- Every intel hit is stored with source name, list version/date and fetch time.
- "Not on any list" is reported as "not found on these lists", never as safe.
- Lists with unclear licenses are downloaded at runtime by the user's own backend, not copied into our repository, until the license is read and confirmed.

## 3. Dataset candidates for the wallet ML model

None has been downloaded or inspected yet, and no license has been read. All are candidates only.

| Candidate | What was found | Concerns |
|---|---|---|
| XBlock MulDiGraph | 2,973,489 nodes, 13,551,303 edges, 1,165 phishing nodes (two-hop graph from known phishing nodes) | Old, graph-shaped, license unverified |
| B4E dataset | Jan 2017 to May 2022; 3,220 phishing and 594,038 normal accounts | License unverified |
| Kaggle "ethereum-frauddetection-dataset" | 9,841 rows, 2,179 fraud (22.14%) per a third-party README | Pre-computed tabular features; we may not be able to reproduce them from raw transactions |
| Hugging Face fesevu/ethereum_fraud_dataset_by_activity | About 115k balanced addresses, labels from Etherscan and curated lists | License not confirmed from the retrieved text |
| Labels from Etherscan "phish-hack" | Used by multiple papers; one repo notes the data was taken off Etherscan | Terms of use for reuse unverified |

Known problems in this field (from the retrieved papers):
- Extreme imbalance: one study found only 1,259 labeled phishing addresses among 500M+ addresses.
- Phishing behavior changes over time, so models trained on old data degrade.
- "Non-fraud" rows are really "unlabeled", not verified safe. Metrics measure agreement with the label list only.

## 4. ML strategy (proposed)

1. Single shared feature module used by training and inference (prevents train/serve skew). A pre-computed tabular dataset is only usable if we can reproduce every feature from provider data.
2. Build our own training set: take labeled addresses with documented provenance, pull their transaction history through our own provider adapter, and compute features with the shared module.
3. Features use only transactions before the address's first public flag, to avoid label leakage.
4. Split by time (train on older, test on newer), not randomly. Report precision, recall, PR-AUC and per-period results. Report the class balance and never report accuracy alone.
5. Baselines first (logistic regression, random forest), XGBoost only if it beats them on the time-split test set.
6. If no dataset passes the license and quality checks, the wallet engine ships with rules and intel only and reports "ML model unavailable". No fake model.
7. Ollama is deferred to the end of the project.

## 5. Decisions needing approval

| # | Decision | Recommendation |
|---|---|---|
| P1 | Primary explorer | Etherscan V2, Blockscout PRO as fallback, throttled to 3 RPS until verified |
| P2 | Node/RPC provider | Alchemy or Infura free tier (limits to be researched before wiring) |
| P3 | Intel sources | OFAC SDN + ScamSniffer + GoPlus, each stored with source and timestamp; license of ScamSniffer addresses checked first |
| P4 | Dataset approach | Own dataset built through the shared feature module; public datasets used only as label sources after license review |

## 6. Open items before Phase 2 provider work

- Create a free Etherscan API key and read the real limits on the account dashboard (do not share the key).
- Choose Alchemy or Infura and read its current free-tier limits.
- Read the license of each dataset and list before use.
