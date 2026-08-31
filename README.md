# Still Open

**Name the open task. Ask if it's done. File what should survive. Close that pile.**

Hackathon: [All Things Agentic](https://allthingsagentichackathon.devpost.com/) — **Taskmaster** track.

## Live API

Hosted on Google Cloud Run: **[https://stillopen-tqodm6o6za-uc.a.run.app](https://stillopen-tqodm6o6za-uc.a.run.app)**

- Health: [`/health`](https://stillopen-tqodm6o6za-uc.a.run.app/health) — reports `env`, `gemini`, `bank`, `clerk`, `run_graph`, `otel`, `armor`.
- Agent registry: [`/v1/agents/registry`](https://stillopen-tqodm6o6za-uc.a.run.app/v1/agents/registry) — introspected from the loaded `RUN_GRAPH` + gateway policy, cannot drift from code.

The unpacked extension talks to this URL by default; no config needed.

## Run the extension

```bash
make install     # uv workspace install
make ext         # builds packages/ext/dist/chrome-mv3
```

Then:

1. Chrome → `chrome://extensions` → **Developer mode** on
2. **Load unpacked** → select `packages/ext/dist/chrome-mv3`
3. Pin the extension, open the side panel

The extension is already pointed at the hosted Cloud Run API above. **Closes are real** — use the **Demo Seed** button in a new window (20 example tabs: Austin listings, UPS tracking, a dictionary lookup, Chase banking). Do not close your personal tabs.

To point at a local API instead (e.g. after `make api`), in the extension service-worker devtools console:

```js
chrome.storage.local.set({ apiBase: "http://127.0.0.1:8080" })
```

## Features

- **Named tasks, not categories.** Framer + Gemini clusters your window by *goal* ("Find a place in Austin") — not by host class ("Housing"). Three Zillow tabs + a Redfin tab + the Google search that started it become one card.
- **"Done, close!"** runs a real multi-agent pipeline: the **Clerk** drafts a filing on Vertex Gemini 3.5, the **Runner** persists it to Firestore with a browsable permalink at `/v1/filings/{id}`, and the **Verifier** re-reads it before green-lighting the close. If the Verifier can't verify, tabs stay open.
- **Trusted user notes.** Notes ride into the Clerk prompt marked *preserve verbatim*; a Python guard rebuilds the "Notes from the user" section if the LLM tried to rewrite it. The Verifier requires the notes to be present *verbatim* in the filed body.
- **Ephemeral short-circuit.** A one-tab dictionary lookup skips the LLM path (`clerk="skipped"`) but still emits an audit event so the transparency story is uniform.
- **"Still going" → hash-only Watch.** Not done yet? The extension enrols a `Watch` that Cloud Scheduler ticks every 5 minutes. We only ever store `sha256(body)`, never the fetched HTML.
- **Auditable per plan.** Every phase (`proposed → clerk_draft → runner_file → verifier_ok → close_applied`) becomes a `PlanEvent` at `GET /v1/plans/{id}/audit`.
- **Undo without leaking.** Original URLs for Undo live in `chrome.storage.session` and never leave the laptop.
- **Bank / health / gov / school / auth hosts never reach a model.** Enforced by the Surveyor before any Gemini call.

## Stack + rubric

| Requirement | What Still Open uses | Where |
|---|---|---|
| **Gemini 3.5+** | `gemini-3.5-flash` (Clerk) and `gemini-3.5-pro` (planner) on Vertex AI | [`gateway/router.py`](packages/core/src/stillopen_core/gateway/router.py) |
| **Google Agent Framework** | ADK `SequentialAgent`: `clerk → runner → verifier` | [`agents/adk_graph.py`](packages/core/src/stillopen_core/agents/adk_graph.py) |
| **≥1 Google Cloud service** | Cloud Run · Firestore · Cloud Scheduler · Secret Manager · Cloud Trace · Model Armor | [`Makefile`](Makefile) `deploy` / `cloud-apis` / `scheduler` |
| Bonus: second Google AI model | Gemma 2 9B on Vertex (opt-in via `STILLOPEN_GEMMA_MODEL`) for task labels | [`gateway/gemma.py`](packages/core/src/stillopen_core/gateway/gemma.py) |
| Bonus: Google embedding model | `text-embedding-004` on Vertex (opt-in via `STILLOPEN_USE_VERTEX_EMBEDDINGS=1`) | [`memory/embeddings.py`](packages/core/src/stillopen_core/memory/embeddings.py) |
| Continuous Action Engine | Cloud Scheduler → `/v1/jobs/watch` on Cloud Run; hash-only fetch, per-tick budget | [`watch/tick.py`](packages/core/src/stillopen_core/watch/tick.py) |
| Evolving Knowledge Engine | `MemoryBank` (Firestore in cloud, JSON in dev) — plans, filings, watches, events, tokens, habits | [`memory/`](packages/core/src/stillopen_core/memory) |
| Multi-Agent Nexus | Surveyor / Framer / Clerk / Runner / Verifier / Auditor; each with its own gateway allowlist | [`ARCHITECTURE.md`](ARCHITECTURE.md#agents--tool-isolation) |
| Security posture | Per-user bearer token (`X-Stillopen-User-Token`); job token (`X-Stillopen-Job-Token`) from Secret Manager; deny-listed hosts never seen by a model; Model Armor on every prompt | [`SECURITY.md`](SECURITY.md) |
| Verifier fidelity | Existence isn't enough — the Verifier reads the filed body and requires that (a) card tab hosts are cited and (b) user notes appear verbatim | [`agents/verifier.py`](packages/core/src/stillopen_core/agents/verifier.py) |
| Server-derived intent | The "should I run Clerk?" decision uses Framer's `infer_intention` on the sanitized tabs — never the client's self-report | [`api/routes/finish.py`](packages/api/src/stillopen_api/routes/finish.py) |

Deep dives: [ARCHITECTURE.md](ARCHITECTURE.md) (topology + agent isolation + auditability) · [SECURITY.md](SECURITY.md) (trust model, deny lists, tokens).

## Layout

```
packages/core/                  agents, gateway, memory, schemas, security, observability
├── agents/                     Framer, Clerk (ADK), Runner, Verifier, Auditor
│   ├── adk_graph.py            SequentialAgent (clerk → runner → verifier)
│   ├── clerk.py                artifact drafting + user-notes guard
│   ├── verifier.py             existence + fidelity + notes-verbatim
│   └── run_conductor.py        run_plan orchestrator
├── gateway/
│   ├── router.py               per-agent tool allowlist + rate limits
│   ├── gemini.py               Vertex Gemini 3.5 client
│   └── gemma.py                optional Gemma 2 task-label side channel
├── google/
│   ├── workspace.py            GoogleWorkspace protocol + FakeGoogle
│   └── filings.py              FilingStore → Firestore + /v1/filings/{id} permalinks
├── memory/
│   ├── fakes.py                in-memory MemoryBank (tests + dev)
│   ├── firestore.py            Firestore-backed MemoryBank (cloud)
│   └── embeddings.py           HashEmbedder + optional VertexEmbedder
├── observability/
│   ├── audit.py                record_event → PlanEvent append-only log
│   └── tracing.py              Cloud Trace / OTEL spans
├── security/
│   ├── hosts.py                bank / health / gov / school / auth deny list
│   ├── redact.py               query-string + fragment stripping
│   └── user_token.py           issue + verify per-user bearer tokens
└── watch/
    ├── enroll.py               Watch from plan / from task ("Still going")
    └── tick.py                 hash-only Watch tick (Cloud Scheduler)

packages/api/                   FastAPI on Cloud Run
├── main.py                     app factory, CORS, health, routers
└── routes/
    ├── finish.py               POST /v1/tasks/finish, POST /v1/tasks/still-going
    ├── auth.py                 POST /v1/auth/register
    ├── audit.py                GET  /v1/plans/{id}/audit
    ├── filings.py              GET  /v1/filings/{id}
    └── agents.py               GET  /v1/agents/registry

packages/ext/                   Chrome MV3 (WXT + React)
└── src/
    ├── entrypoints/
    │   ├── background.ts       tab close / undo / messaging
    │   └── sidepanel/          Workbench, UndoView, App
    └── lib/
        ├── api.ts              typed client to Cloud Run (finish, still-going, register)
        ├── schema.ts           zod schemas mirroring the API
        └── tabs.ts             CloseBatch + undoMap in chrome.storage.session

packages/jobs/                  Watch tick entrypoint (Cloud Run job)
fixtures/                       synthetic house-hunt window only (no real user tabs)
tests/                          114 pytest, incl. verifier fidelity + server-intent
Makefile                        make api / make ext / make deploy / make scheduler
```
