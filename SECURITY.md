# Security — why this extension is allowed to see tabs

Still Open reads tab **metadata** so it can name unfinished jobs and close that pile. That is enough to leak a life if we are sloppy. These rules are code, not vibes. Judges: this is the tab trust model.

```
Chrome tab metadata
        ├─► chrome.storage.session   original URLs for Undo (laptop only)
        └─► Surveyor redact ──► API / Firestore
                    │
                    ├─ deny-listed host ──► blocked_from_model (never Gemini)
                    └─ other hosts ──► cluster sees title + host + redacted URL
```

## What we read (default)

Title, URL, window/index, pinned, audible, discarded, group id, `lastAccessed`.

No page HTML. No cookies. No history API. Snapshots are `http(s)` only ([`packages/ext/src/lib/tabs.ts`](packages/ext/src/lib/tabs.ts)).

## What never leaves the laptop

Original URLs for Undo live in `chrome.storage.session` (`undoMap` / `lastClosed`). The API gets a **redacted** snapshot ([`redact.py`](packages/core/src/stillopen_core/security/redact.py)): secret query keys → `REDACTED`, fragment dropped. Firestore stores that same redacted shape — not the session undo map.

A personal tab dump would leak bank URLs, school portals, and auth tokens in query strings. That is why fixtures are synthetic and why we refuse to commit or chat a live window.

## What never goes to a model

Bank / health / gov / school / auth hosts: no extracts, no Clerk prompt body ([`hosts.py`](packages/core/src/stillopen_core/security/hosts.py) `NEVER_MODEL_CLASSES`). The demo Chase tab is the proof. Embeddings are title+host only. Logs: host+path, never query string.

## Permissions

| Permission | Why |
|---|---|
| `tabs` | Read title/URL/`lastAccessed` for the workbench and daily sweep |
| `tabGroups` | See Chrome's existing groups; we do not restyle them |
| `sidePanel` | The workbench |
| `storage` | `apiBase`, `userId`, cutoff — not original Undo URLs |
| `alarms` | Daily sweep badge + user-chosen scheduled closes |
| `http://127.0.0.1:8080/*` | Local API |
| `https://*.run.app/*` | Cloud Run API when judges use the hosted URL |
| optional `https://*/*` | Not used at install. We do not inject all pages |

Never `<all_urls>` at install. Page bodies are not read for the demo.

## Close is a privilege

User uncheck / Undo / skip teaches keep. Scheduled close only URLs the user selected. Watch stores **hashes**, never HTML.

## Authenticated writes

The `POST /v1/tasks/finish` and `POST /v1/tasks/still-going` endpoints — the two paths that mutate durable state on the user's behalf — accept an optional `X-Stillopen-User-Token` bearer header. The extension registers once at install (`POST /v1/auth/register`), the token is stored in `chrome.storage.local`, and the server keeps only its SHA-256 hash. Turn on `STILLOPEN_REQUIRE_USER_TOKEN=1` in production and a mismatch is a 401. The token is regenerated with 32 bytes of `secrets.token_hex`, so brute-forcing it is not feasible; comparison is constant-time (`secrets.compare_digest`) so timing side-channels are neutralised. See [`user_token.py`](packages/core/src/stillopen_core/security/user_token.py).

Cloud Scheduler proves it's Cloud Scheduler with `X-Stillopen-Job-Token` from Secret Manager; the token is checked on every `/v1/jobs/watch` call in cloud.

## Auditability

Every plan has an append-only trail at `GET /v1/plans/{id}/audit` (Firestore in cloud, JSON on disk locally). Every Clerk-drafted filing has a permalink at `GET /v1/filings/{id}`. `GET /v1/agents/registry` returns the exact tools each agent is allowed to call and their rate limits, read from the loaded gateway policy — nothing to keep in sync by hand.

## Data we will not handle

- No real personal window as a fixture or in git.
- No bank, medical, government, school SIS, or auth-host **page bodies** to Gemini.
- No OAuth refresh tokens in the extension, in logs, or in plaintext files.
- No query strings in logs (host + path only).

If you paste secrets in chat: rotate the key. Do not paste `.env`, service-account JSON, or a live tab export here.
