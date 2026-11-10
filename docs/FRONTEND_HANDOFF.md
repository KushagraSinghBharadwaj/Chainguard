# ChainGuard frontend handoff (10 November 2026)

Branch: `web-next-frontend` (not merged into `main`).

## How to run
- Backend, from the repo root: `python -m uvicorn app.main:app --port 8000`
- Website: `cd web-next` then `npm run dev -- --port 5174 --strictPort`
- Extension: `chrome://extensions` > Load unpacked > `C:\Dev\chainguard\extension` (version 0.3.0). Reload it after every edit. It has no build step.
- The extension's website links use `const SITE = "http://localhost:5174"` in `extension/popup.js` and `extension/content.js`. Change both when the site is deployed.

## Status
| Area | State |
| --- | --- |
| Backend through Phase 10 | Complete (backend tests need a fresh run) |
| Website: landing, scan, report, history, dashboard | Working, confirmed by owner |
| Website: About, Docs, PDF download, cursor effects | Working, confirmed by owner |
| Extension popup: Wallet, Token, Transaction, History, Docs tabs, hover motion, website links | Working, confirmed by owner |
| Extension on-page overlay linked to MetaMask | Built, NOT yet tested on a real page on Ethereum mainnet |
| Website Connect Wallet (`/wallet`, bottom-right pill) | Built, build passes, browser test pending |
| Full 70-item frontend test checklist | Not done |
| Accessibility and responsive audits | Not done |
| 3D shield, extension info page | Not done |
| Deployment | Not done (localhost links only work on this PC) |

## Decisions
- Ethereum mainnet only. Sepolia and other chains are future work.
- Wallet connection uses EIP-6963 directly (MetaMask, Rabby, Coinbase Wallet, Trust Wallet). No Wagmi or WalletConnect yet. Glow (Solana) needs a separate integration.
- The extension and the website use different client tokens, so extension links open website pages, not a specific report.
- Risk levels come only from the deterministic rules engine. The ML signal is marked not reliable and the local-model rewrite never changes the level.
- ChainGuard is advisory: if it fails, a wallet request still goes through.

## Next steps
1. Browser-test Connect Wallet, then Rabby, Coinbase and Trust if installed.
2. Test the MetaMask overlay on Ethereum mainnet using the Reject button only (`cd extension-test; python -m http.server 8080`).
3. Website Scan page: read `?address=` so extension links can pre-fill the address.
4. Work through the test checklist, then accessibility and responsive audits.
5. Deploy the site and backend, then update `SITE` in the extension.

## Gotchas
- `web-next` was restored from the `web-next-frontend` branch. The untracked copy is at `C:\Dev\web-next-backup` and can be deleted once everything is verified.
- When patching files from PowerShell, check that each anchor string exists before replacing it.
