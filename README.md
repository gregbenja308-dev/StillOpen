# Still Open

**Name the open task. Ask if it is done. Close that pile.**

Hackathon: [All Things Agentic](https://allthingsagentichackathon.devpost.com/) — **Taskmaster**.

Gemini 3.5 on **Vertex AI**, **Google ADK** Clerk, **Cloud Run + Firestore + Cloud Scheduler**. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Trust model: [SECURITY.md](SECURITY.md).

```
Extension snapshot → named tasks (Chrome groups + Framer + Gemini)
        → I'm done → close that pile (notes stay in Restore)
        → Cloud Scheduler → hash-only Watch tick
```

The workbench is **named tasks**, not categories. Notes are the done-path when the job should survive the tab strip. A word-lookup just closes.

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

**Closes are real.** Use the synthetic demo window, not your personal tabs.

```bash
# Workbench
Open demo tabs → “Find a place in Austin” → notes → I’m done → Restore
```

## Production (Cloud Run)

Judges: hosted URL is the API. Point the extension `apiBase` at it.

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

Confirm `/healthz` shows:

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
| Gemini 3.5+ via Vertex or Gemini API | Vertex: `GOOGLE_GENAI_USE_VERTEXAI=true`, models `gemini-3.5-flash` / `gemini-3.5-pro` |
| Google Agent Framework | ADK `LlmAgent` Clerk + SequentialAgent graph |
| Google Cloud infrastructure | Cloud Run, Firestore, Cloud Scheduler, Cloud Trace, Secret Manager |

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
