# Still Open

**People leave tabs open because a task is not done. We name the task, ask if it is done, then close that pile.**

**Hackathon:** [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
**Track:** Taskmaster
**Deadline:** Aug 31, 2026 @ 5:00pm PDT
**Required stack:** Gemini 3.5+ · Google Agent Framework (ADK / GenAI SDK / Antigravity SDK / GenKit) · ≥1 Google Cloud service

A second submission next to [Level](level/README.md) (Collaborative Partner). The FAQ allows more than one project if each is unique and substantially different. Level is about *time and care*. Still Open is about *the window you have not closed*.

Name: **Still Open** — not AgentFlow, not TabPilot.

---

## Product direction (lock this)

People open tabs to **do something**. The something can be tiny (what does this word mean) or large (find a house to rent). They will not close those tabs until they feel **done with that task**. Category buckets (“News”, “Housing”) are the wrong unit. Chrome already groups by similarity. We group by **goal**.

**Loop:**

1. Read the window: titles, URLs, `lastAccessed`, and **the user’s existing Chrome tab groups** (a group the human made is a strong task prior — we do not restyle it).
2. Infer **named tasks**, not host classes. Example: “Find a house to rent” covering three Zillow tabs + a Redfin tab + the Google search that started it. A dictionary lookup is its own small task.
3. Ask, in plain language: *Have you finished finding a house to rent?*
4. If **yes** → close the related tabs (Restore can rewind). If the task produced work worth keeping (a comparison, a tracking date), **File** that pile into Google *as the done-path*, then close. A word-lookup does not get a Doc.
5. If **not yet** → leave the pile. Optionally Watch (calendar a check). Do not nag-close.

**File is not the product.** File is what “done” looks like when the job should survive the tab strip (house hunting → one comparison Doc). Chrome history already has the URL; it does not have the *task*. Small tasks skip File.

**What we will not do:** restyle the tab strip, auto-close because a tab is “news” or unused for 7 days without naming the task, or treat Chrome’s “Shopping” group as the answer.

### Features this implies

| Ship | Not this |
|---|---|
| Workbench of **named tasks** (“Find a house to rent”, “Look up ephemeral”) | Daily sweep grouped by category |
| “Are you done with X?” → Close these N tabs | “Close all housing tabs” as the default ask |
| Use Chrome groups as a hint for task boundaries | Invent new colored groups |
| File only when the done-task is durable | File every close into a Doc |
| Restore tab for last close | Sticky undo dock on the workbench |

### Implementation this implies

- **Framer output = tasks**, each with a human label + member `tab_ids`. Host class is a feature, not the cluster key. Gemini (ADK Clerk / a classify step) names the goal from titles+hosts+group names.
- **Chat/workbench ask** is done-or-not on a task, not “delete news.”
- **Close set** = that task’s tabs, user-confirmed. Bank/gov/health still never go to the model.
- **File** (Docs/Calendar) runs only on tasks whose “done” is an artifact (comparing, waiting). Heuristic: comparing/listings → Doc; waiting → event; lookup/zombie → close only.
- **Sweep** becomes “tasks you have not opened in N days — still going?” not unused-URL categories.

### Honest gap vs code today (2026-08-18)

The workbench is **named tasks**. Chrome group titles are a prior. Ungrouped listings plus the search that started them become one goal (“Find a place in Austin”). I’m done on a durable job still Files into Google, then closes only if `artifacts_ok`. Ephemeral jobs close only. Chase/gov/health never go to a model. Category sweep (`heuristic_groups`) remains as a test helper, not the UI.

---

## Why this is a new idea

The crowded product is “smart tab groups.” That slot is taken.

| What already exists | What it asks | What it does |
|---|---|---|
| Chrome **Tab Organizer** | What is this *about*? | Suggests named/colored groups. Manual trigger. You still own the pile. |
| **Ask Gemini about this group** (Canary) | What’s *in* these tabs? | Summarize, pin/unpin. Chat over a cluster. |
| OneTab / Session Buddy / The Great Suspender | How do I *hide* this? | Park URLs. No finishing. |
| Pocket / Reading List | Will I read this *later*? | Save. Rarely file. Almost never act. |
| Web Store “AI tab organizers” | Same as Chrome | Cluster by domain or topic. |

Still Open is new because the **unit of work is the unfinished task**, not the URL cluster.

- Chrome: six listing tabs → a group called “Housing.”
- Still Open: those tabs → one named task, “Find a house to rent.” We ask if that task is done. If yes, we close *that* pile — and File a comparison Doc only because the decision should outlive the tabs.

A summarizer that leaves 40 tabs open is a chatbot. A grouper that leaves 40 tabs open is Chrome. An agent that **asks if the task is done** and closes the related tabs is a Taskmaster.

It is also not Level. Level challenges a *yes* against care roles. Still Open challenges a *tab* against the reason you have not closed it.

---

## How it would work

### 1. Snapshot the window

A Chrome extension reads the current window: title, URL, group (if any), last-accessed, pinned, audible. Optional: a short extract of visible page text where the user has granted permission (forms, articles — not a silent scrape of everything).

That snapshot goes to Cloud Run. Nothing clever happens in the extension except apply / undo.

### 2. Classify intention, not topic

Gemini 3.5 labels each tab (and sometimes a *set* of tabs) as one of:

| Intention | Signal | Done looks like |
|---|---|---|
| **Waiting** | tracking, “application status,” “we’ll email you,” portals | Calendar/Task to check; optional No-Show; tab may stay in a saved group |
| **Comparing** | N similar product/job/housing URLs | One Doc: table + links + a recommended pick. User locks; losers close |
| **Read later** | articles, PDFs, long docs, no form | One Drive doc: URL + 3-line abstract + quote. Tabs close |
| **Half-done** | forms, checkout, tax, school portal | Prefill from Calendar/Drive where safe; **Hold** until Run |
| **Reference** | open beside a Doc/Sheet you’re writing | Citations/links dropped into that Doc; then close |
| **Zombie** | duplicate, login wall, error, 3 days untouched | Close; optional bookmark in a dated Drive folder |

Topic can still be a *label* (“laptops,” “field trip”). It is not the routing key. Two GitHub tabs can be Reference (for the PR you’re writing) and Waiting (Actions run) in the same window.

### 3. Propose a workbench, not a chat

The UI is a board of **verbs**, grouped by intention:

- **File** — write the Doc / folder, then close  
- **Watch** — calendar the check, keep a saved group  
- **Finish** — draft the form/mail, wait for Run  
- **Decide** — comparison table, you pick  
- **Kill** — close, no artifact (zombies, vetoes)

You can veto a classification (“that’s not waiting, that’s reference”). Vetoes stick in Memory so the next snapshot does not re-litigate.

Irreversible moves (send mail, submit form, close a tab you marked keep) wait behind **Hold / Run / Kill** — same editor posture as The Fuse, applied to a window.

### 4. Land in Google, then prove it

The Runner agent calls real APIs:

- **Docs / Drive** — comparison table, reading dump, dated “cleared from Chrome” folder  
- **Calendar / Tasks** — watch dates, “finish the form Thursday”  
- **Gmail** — optional “here’s the one-pager from those tabs” to yourself  
- **Saved tab groups** — only for Waiting (must stay live)  
- **Bookmarks** — last-resort shelf, not the product

Then the extension applies the plan: close, group, or leave. Undo restores the previous tab layout (Chrome sessions API / a snapshot you kept).

### 5. Overnight / on a timer (so it is a workflow)

Optional Cloud Scheduler pass:

- Waiting tabs: if the tracking page changed, ping; if the deadline passed, escalate (No-Show)  
- Read-later Doc: if you never opened it in 7 days, don’t nag forever — mark stale  
- Half-done: remind once, with the draft still attached  

The heavy lifting is the first clear. The timer is how you show Taskmaster “without you guiding each step.”

---

## Agents

| Agent | Job |
|---|---|
| **Surveyor** | Snapshot tabs (+ optional extracts). Strip secrets before they leave the machine where possible. |
| **Framer** | Cluster by *intention* (a compare-set is one job, not six). |
| **Clerk** | Draft the Google artifacts (Doc, event, mail). Cite source URLs. |
| **Runner** | Execute locked actions: Drive/Calendar/Gmail + tell the extension to close/group. |
| **Verifier** | Confirm the Doc exists, the event exists, the tabs are gone. Undo log. |

Model Armor on extracts (account numbers, medical portals, school IDs). The Clerk is not allowed to paste a full tax form into a Doc.

---

## Why the design is actually hard

This should feel like Level’s care-load graph: a real visual problem, not a side panel of summaries.

- **Intention vs. topic.** Shopping vs. “I’m waiting for the order email” look similar in the URL. The model has to use recency, duplicates, and page type — and take correction.
- **A set is the object.** Six laptop tabs are one Decide card, not six File cards. The UI has to show the set.
- **Close is a side-effect.** If File writes a thin Doc and kills the tabs, you have destroyed evidence. Abstracts must be good enough to close.
- **Undo is the product.** Same as Kill on The Fuse. If close cannot rewind, people will not let it run.
- **Permission boundary.** Reading page HTML is power and a privacy hole. Default to title/URL; opt in to extract per site class (article vs. bank).
- **Don’t fight Chrome.** Never restyle the tab strip into fake groups. The workbench is a side panel / new tab. Chrome keeps groups.

---

## Killer demo (4 minutes)

Seed a window: 3 laptop listings, 2 tracking pages, 4 articles, 1 duplicate, 1 half-filled school form (fixture).

1. Click **Clear this window**. Workbench appears: one Decide, one Watch, one File, one Finish, one Kill.  
2. Lock Decide → Doc opens with a table; you pick one; four shopping tabs close.  
3. File → Drive doc with abstracts; article tabs close.  
4. Watch → Calendar “check order Friday”; tracking tabs collapse into a saved group.  
5. Kill the duplicate. Finish stays on Hold.  
6. Cut to Cloud Run / Vertex / the live Doc URL.

Fifteen-second beat: **tabs gone, Doc and event exist.** Not “here’s a summary of your tabs.”

---

## Stack

| Requirement | Where it lives |
|---|---|
| Gemini 3.5+ | Intention classify + abstracts + comparison table + form draft |
| ADK | Surveyor → Framer → Clerk → Runner → Verifier |
| Cloud | Cloud Run, Firestore (vetoes, snapshots, undo), Cloud Scheduler (watches), Secret Manager (OAuth) |
| Client | Chrome extension (tabs, tabGroups, bookmarks, identity) |
| Google landing | Docs, Drive, Calendar, Gmail, Tasks |
| Guardrails | Model Armor on page extracts; least privilege OAuth scopes |

---

## Honest crowding / failure modes

- If the first frame is colored tab groups, judges will say “Chrome already does that.” Lead with the workbench and the Doc.  
- If you only summarize, you are Glic / “Ask Gemini about this group.”  
- If you only save links, you are OneTab.  
- Shopping *Decide* can look like Google Shopping. Keep the demo mixed (research + waiting + form), not six Amazon tabs.  
- Extensions that auto-close tabs have a trust problem. Hold/Run/Undo are not optional polish.

---

## vs. other ideas in this repo

| Idea | Track | Object |
|---|---|---|
| Level | Collaborative Partner | A yes vs. care roles |
| Places | Taskmaster (shelved) | A room photo vs. a floor plan |
| The Fuse | Taskmaster | A letter vs. a clock |
| Still Signed In | Fleet | Residue on a machine, least privilege |
| **Still Open** | **Taskmaster** | **A tab vs. the reason it is still open** |

Still Open can *feed* Still Signed In (a leftover school session tab) without being the same product: one clears a window into Google; the other revokes grants on a laptop.

---

## Judging alignment (all three engines)

Track is **Taskmaster**. Judges still score Continuous Action, Evolving Knowledge, and Multi-Agent Nexus. Still Open is built to hit all three without becoming a chatbot or Chrome Tab Organizer.

**Unlikely Hero:** the person whose working memory *is* the tab strip — a parent mid-housing-search, a student with twelve portals, anyone who does not have an EA. Not a corporate productivity OS.

### Innovation & Operational Utility (40%)

| Rubric ask | Design decision |
|---|---|
| Eliminate real friction / Twist | Unit of work is the *named task* (find a rental, look up a word), not a topic cluster. We ask if it is done, then close that pile. File is the done-path for durable jobs. |
| Taskmaster: multi-step background without you | After Run, Watch rows tick on a timer: hash the tracking page (never store HTML), Task if it changed, Calendar No-Show if the deadline passed. Extension not required. |
| BYOF | A real messy window (housing + articles + a bank tab that must never be sent to the model). |
| Collaborative Partner: mutate data | HabitProfile mutates on explicit Uncheck / Undo / Veto only. Next snapshot does not re-litigate. |
| Unusual messy streams | Mixed window: listings, SERP leftovers, news, duplicates, deny-listed bank. Surveyor redacts before any model. |
| Fleet: specialized sub-agents | Surveyor / Framer / Clerk / Runner / Verifier. Clerk cannot execute. Runner cannot draft. Verifier cannot mutate. |
| Unlikely Hero | Tab-as-memory for people without an EA — not a PM copilot. |

### Architectural Discipline (30%)

| Rubric ask | Design decision |
|---|---|
| Continuous Action: modular, state, scoped tools | `core` / `api` / `jobs` / `ext`. Firestore-shaped MemoryBank (in-memory now). Gateway allowlists. Close is last and forbidden if File failed. |
| Evolving Knowledge: schema, embeddings, context | Habit pins stay hot (≤8). Tab vectors are title+host only (64-d hash locally; Vertex + `user_id` restrict in cloud). Prompt cap 12 tabs; extracts never from deny-listed hosts; 2k char cap. |
| Multi-Agent Nexus: SoC + failure tolerance | Sequential Run: Clerk → Runner → Verifier. Clerk invalid JSON → retry once → degrade. Google write fails → no close. Hallucinated extra keys forbidden by schema. |

---

## Open questions

- First-run permission: title/URL only, or opt-in extracts for articles/forms?
- Where does the workbench live — side panel, new tab, or a Cloud Run app the extension opens?
- How aggressive is auto-clear vs. always propose-then-Run for v1? (Propose-then-Run is the safer demo.)
- Do we sync vetoes across devices (Chrome profile) or keep them in Firestore keyed to Google account?
