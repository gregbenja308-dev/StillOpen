# 4-minute unedited beat

Record on the demo window. Do not dump a personal window.

1. **Friction (20s)** — Demo opens a messy window: Austin listings, a dictionary lookup, laptops, UPS, news, Chase. Say: “Chrome did not finish this. These are unfinished tasks.”
2. **Twist (15s)** — “Still Open names the task — find a place in Austin — and asks if you are done.”
3. **Done, then close (90s)** — Open the Austin task, type a note, hit **Done, close!**. Tabs gone. Restore lists exact titles and the note. Chase never moved.
4. **Still going (20s)** — Restore, hit **Still going**. Memory shows a keep. Tabs stay.
5. **Without you (40s)** — Cloud Console: Scheduler job → `POST /v1/jobs/watch`. Hash-only tick. No-Show or page-change Task.
6. **GCP (25s)** — Cloud Run `/healthz` (`env: cloud`, `gemini: vertex`, `bank: firestore`, `otel: gcp`) + Firestore `plans` / `habits` + Cloud Trace spans `stillopen.run_plan`.
7. **Bank stays off the model (20s)** — Chase card: “Stays. Never sent to a model.” Surveyor / Clerk prompt: `blocked_from_model`.

Talking line if asked about tabs: “We read title, URL, and your existing group name. Undo URLs never leave this laptop. Bank hosts never go to Gemini.”
