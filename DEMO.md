# 4-minute unedited beat

Record on the synthetic demo window. Never dump a personal window.

1. **Friction (15s).** Load the demo tabs: three Austin listings, a UPS tracking page, a dictionary lookup, laptops on a shopping site, news, and a Chase online-banking tab. Say: *"Chrome did not finish this. These are unfinished tasks — and closing them all just erases what I still owe someone."*

2. **The workbench (20s).** Open the side-panel. Point at the two named tasks the extension inferred: **"Find a place in Austin"** (3 tabs) and **"Track UPS delivery"** (1 tab). Point at the dictionary lookup labelled *ephemeral* and the Chase card labelled *protected — never sent to a model*.

3. **Notes → Done, close! (75s).** Type into the Austin task's notes field: *"3 bed, under $3200, walkable to trailhead."* Hit **Done, close!**.
   - Cloud Run receives `POST /v1/tasks/finish`.
   - The **Clerk** (ADK `LlmAgent` on Gemini 3.5 flash) drafts a "House shortlist" filing.
   - The **Runner** files it into Firestore and returns a permalink.
   - The **Verifier** re-reads the filing, sees the citations, green-lights the close.
   - The extension closes the three Austin tabs atomically.
   - In the *Finished* panel, click the **Filing** link. Open the filing at `/v1/filings/{id}`: judges see the exact bytes the LLM drafted, the citations back to Zillow/Redfin, and — verbatim — the note *"3 bed, under $3200, walkable to trailhead."*
   - Click the **Audit trail** link. `GET /v1/plans/{id}/audit` shows the chain: `proposed → clerk_draft → runner_file → verifier_ok → close_applied`.

4. **The ephemeral path (15s).** Do a dictionary lookup task and press **Done, close!**. Nothing files, one audit event fires (`close_applied`, agent `framer`), Chase stays open, and the badge says *ephemeral: closed without a filing*.

5. **Still going (25s).** On the UPS task, hit **Still going**. `POST /v1/tasks/still-going` enrols a hash-only `Watch`. In Cloud Console show the Cloud Scheduler job hitting `/v1/jobs/watch`; the watch's status flips to `PAGE_CHANGED` when the ship status updates. No page HTML in Firestore, only `sha256(body)`.

6. **Agent registry (15s).** `curl https://…run.app/v1/agents/registry`. Point at `graph: clerk>runner>verifier`, at each agent's `tools`, at Clerk's `model: gemini-3.5-flash`, and at the per-tool `rate_limits_per_minute` — read straight from the loaded gateway policy, not from a hand-written doc.

7. **GCP proof (30s).** Cloud Run `/health` (`env: cloud`, `gemini: vertex`, `bank: firestore`, `otel: gcp`, `run_graph: clerk>runner>verifier`, `armor: model_armor`). Firestore console: `plans/`, `filings/`, `watches/`, `plan_events/`. Cloud Trace: the span `stillopen.run_plan` with child spans `clerk.draft`, `runner.file`, `verifier.check`.

8. **Bank stays off the model (15s).** Open the Chase card in the workbench. Say: *"This one is protected — bank host on the deny list. Its title and URL are stripped before the prompt is built. Model Armor sits between the Clerk and Gemini either way."* Show the Surveyor debug view: Chase's `blocked_from_model=true`.

9. **Security posture (10s).** *"Every `finish` and `still-going` write carries a per-user bearer token the extension registered at install; the server keeps only its SHA-256 hash. Cloud Scheduler proves it is Cloud Scheduler with a Secret-Manager-hosted job token. Original Undo URLs never leave the laptop."*

**One-liner if a judge asks what's new:** *"The done-path is a multi-agent ADK graph with a Verifier veto, an auditable trail per plan, a filing you can point a browser at, hash-only Watches for the tabs you're not done with, an introspected agent registry, per-user bearer tokens on the write paths, and Model Armor on every prompt."*
