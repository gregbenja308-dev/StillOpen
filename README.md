# Still Open

**Name the open task. Ask if it is done. File what should survive. Close that pile.**

Hackathon: [All Things Agentic](https://allthingsagentichackathon.devpost.com/) — **Taskmaster**.

Gemini 3.5 on **Vertex AI**, an **ADK SequentialAgent graph** (Clerk → Runner → Verifier), **Cloud Run + Firestore + Cloud Scheduler + Secret Manager + Cloud Trace + Model Armor**. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Trust model: [SECURITY.md](SECURITY.md).

```
Extension snapshot → named tasks (Chrome groups + Framer + Gemini)
   → Done, close! → /v1/tasks/finish
       → Clerk (ADK) drafts artifacts
       → Runner files to FilingStore (Firestore, permalinks at /v1/filings/{id})
       → Verifier re-reads and green-lights the close
       → Chrome closes the tabs atomically
   → Finished panel shows filing + audit-trail links
   → Still going? → /v1/tasks/still-going → hash-only Watch (Cloud Scheduler)
```

The workbench is **named tasks**, not categories. Notes ride into the Clerk prompt as trusted content and are re-enforced verbatim by a Python guard so an LLM cannot rewrite them. A one-tab lookup short-circuits the LLM path (`clerk="skipped"`) but still emits an audit event so the transparency story is uniform.

## Judges: the one-endpoint story

- `POST /v1/tasks/finish` — the primary done-path, runs the full ADK graph, returns `{plan, apply, report, filing_urls, audit_url, clerk}`.
- `GET  /v1/plans/{id}/audit` — the append-only chain: `proposed → clerk_draft → runner_file → verifier_ok → close_applied`.
- `GET  /v1/filings/{id}` — the exact bytes the Clerk drafted, with citations back to the source URLs.
- `GET  /v1/agents/registry` — introspected from `RUN_GRAPH` + the loaded gateway policy; cannot drift from code.
- `POST /v1/tasks/still-going` — enrol hash-only Watches; drives the Continuous Action Engine loop.
- `POST /v1/auth/register` — one-time per install; issues a per-user bearer token whose hash is what the server stores. Enforced when `STILLOPEN_REQUIRE_USER_TOKEN=1`.

## Why this extension is allowed to see tabs

It reads **title, URL, lastAccessed** — not page HTML, cookies, or history. Original URLs for Undo stay in `chrome.storage.session`. The API gets a redacted snapshot. Bank / health / gov / school / auth hosts never go to a model.

## Local setup

```bash
make env
make token-key          # paste into STILLOPEN_TOKEN_KEY
# Vertex (GCP credits): GOOGLE_CLOUD_PROJECT + GOOGLE_GENAI_USE_VERTEXAI=true
# then: gcloud auth application-default login
# or paste GOOGLE_API_KEY (AI Studio). Do not commit.
make install
make test
make api                # http://127.0.0.1:8080/healthz
make ext                # packages/ext/dist/chrome-mv3
```

Chrome → `chrome://extensions` → Developer mode → Load unpacked → `packages/ext/dist/chrome-mv3`.

The unpacked build talks to the hosted Cloud Run API. To use a local API instead, in the extension service worker console:

```js
chrome.storage.local.set({ apiBase: "http://127.0.0.1:8080" })
```

**Closes are real.** Use the synthetic demo window, not your personal tabs.

```bash
# Workbench
Open demo tabs → “Find a place in Austin” → notes → I’m done → Restore
```

## Production (Cloud Run)

Judges: hosted API is https://stillopen-tqodm6o6za-uc.a.run.app (health: `/health`). Load unpacked `packages/ext/dist/chrome-mv3` — it uses that URL by default.

```bash
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export GOOGLE_CLOUD_REGION=us-central1
export GOOGLE_CLOUD_LOCATION=global
gcloud auth login
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud auth application-default login

make cloud-apis
make secrets-init
make cloud-iam
make deploy
# Copy the https://….run.app URL, then:
export STILLOPEN_JOB_TOKEN=$(gcloud secrets versions access latest --secret=stillopen-job-token)
make scheduler URL=https://stillopen-xxxxx.run.app
```

Confirm `/health` shows:

| Field | Production value |
|---|---|
| `env` | `cloud` |
| `gemini` | `vertex` |
| `bank` | `firestore` |
| `clerk` | `adk` |
| `run_graph` | `clerk>runner>verifier` |
| `otel` | `gcp` |
| `armor` | `inline` (or `model_armor` if a template is set) |

Secret Manager ids (loaded at boot if env is empty): `stillopen-job-token`, `stillopen-google-api-key`.

## Stage One checklist (mandatory)

| Requirement | This repo |
|---|---|
| Gemini 3.5+ via Vertex or Gemini API | Vertex: `GOOGLE_GENAI_USE_VERTEXAI=true`, models `gemini-3.5-flash` (Clerk) / `gemini-3.5-pro` (planner) |
| Google Agent Framework | ADK `SequentialAgent` (`clerk → runner → verifier`) in [`adk_graph.py`](packages/core/src/stillopen_core/agents/adk_graph.py) |
| Google Cloud infrastructure | Cloud Run, Firestore (MemoryBank + Filings), Cloud Scheduler (Watch), Cloud Trace (OTEL), Secret Manager, Model Armor |
| Optional second Google AI model | Gemma 2 9B on Vertex for task labels (`STILLOPEN_GEMMA_MODEL=gemma-2-9b-it`) |
| Optional Google embedding model | `text-embedding-004` on Vertex behind `STILLOPEN_USE_VERTEX_EMBEDDINGS=1` |

## Video

Unedited 4-minute beat: [DEMO.md](DEMO.md). Must show Cloud Run `/healthz` and Scheduler.

## Layout

```
packages/core   schemas, redaction, ADK Clerk, Runner, Verifier, MemoryBank, gateway
packages/api    FastAPI (Cloud Run)
packages/jobs   Watch tick
packages/ext    Chrome MV3 (WXT / React)
fixtures/       synthetic house-hunt window only
ARCHITECTURE.md production topology
```
