# Still Open

Treat an open tab as unfinished business. **File it into Google, then close.**

Hackathon: [All Things Agentic](https://allthingsagentichackathon.devpost.com/) — **Taskmaster**.

```
Extension snapshot → Surveyor redact → Framer
        → ADK Clerk (Gemini 3.5) → Runner (Docs/Calendar) → Verifier
        → close only if artifacts_ok → Watch enroll
        → Cloud Scheduler → hash-only tick
```

Chat is a side channel. The scoring beat is **File first, close last**.

## Why this extension is allowed to see tabs

It reads **title, URL, lastAccessed** — not page HTML, cookies, or history. Original URLs for Undo stay in `chrome.storage.session`. The API gets a redacted snapshot. Bank / health / gov / school / auth hosts never go to a model.

See [SECURITY.md](SECURITY.md) for the permission table and data flow.

## Local setup

```bash
make env
make token-key          # paste into STILLOPEN_TOKEN_KEY
# paste GOOGLE_API_KEY (AI Studio). Do not commit.
# optional: GOOGLE_OAUTH_CLIENT_ID / SECRET for live Docs
make install
make test
make api                # http://127.0.0.1:8080/healthz
make ext                # packages/ext/dist/chrome-mv3
```

Chrome → `chrome://extensions` → Developer mode → Load unpacked → `packages/ext/dist/chrome-mv3`.

**Closes are real.** Docs are fake until you connect the throwaway Google account (`/v1/auth/google`). Use the synthetic demo window, not your personal tabs.

```bash
# Workbench
Open demo tabs → Ask “house shopping” → File, then close → Undo lists exact sites
```

## Cloud (judges)

| Piece | Why |
|---|---|
| Cloud Run | FastAPI: plans, memory, OAuth, `POST /v1/jobs/watch` |
| Firestore | MemoryBank (`plans`, `habits`, `watches`, `artifacts`, `scheduled`) |
| Cloud Scheduler | 15–60 min hash-only Watch tick |

```bash
# After gcloud auth, on the Still Open project (not Level's):
make deploy
```

Set `STILLOPEN_ENV=cloud`, `GOOGLE_CLOUD_PROJECT`, Secret Manager for `GOOGLE_API_KEY` / `STILLOPEN_TOKEN_KEY` / OAuth. Scheduler: `POST https://<service>.run.app/v1/jobs/watch` with `X-Stillopen-Job-Token`.

Judge URL: `https://<service>.run.app/healthz`

## Video

Unedited 4-minute beat: [DEMO.md](DEMO.md).

## Layout

```
packages/core   schemas, redaction, ADK Clerk, Runner, Verifier, MemoryBank
packages/api    FastAPI (Cloud Run)
packages/jobs   Watch tick
packages/ext    Chrome MV3 (WXT / React)
fixtures/       synthetic house-hunt window only
```
