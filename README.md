# PACT Agentic QE Orchestration Platform

An agentic Quality Engineering orchestration platform for Salesforce delivery
(FSC / Sales Cloud / Marketing Cloud) in an FCA-regulated wealth-management
environment. Built on the **PACT** model (Proactive, Autonomous, Collaborative,
Targeted) with strict **human-in-the-loop** controls:

1. **No agent ever starts without an explicit, recorded human approval.**
2. **Every phase ends with a formal, named Gate Sign-Off** before the next
   phase unlocks. Gate order is strict: Refinement → Development → Testing → Release.
3. **Every decision is written to an append-only, hash-chained audit trail**
   (designed for 7-year FCA retention). FCA-scenario and Financial Data
   Integrity failures are always release-blocking — no override exists.

## Build status

| Step | Scope | Status |
|---|---|---|
| 1 | Backend skeleton: domain model, run/gate state machines, hash-chained audit log, mock Jira adapter, demo seed | ✅ done |
| 2 | Full Jira integration: REST v3 adapter (search/jql pagination, ADF, dynamic transitions), configurable field mappings, push queue (preview → approve → send → retry), per-gate auto comment/label/transition, release audit-pack attachment, settings API, scheduled sync | ✅ done (37 tests passing) |
| 3 | Agent engine: Claude API (structured outputs via `messages.parse`, adaptive thinking), file-based versioned prompt registry (`backend/prompts/<agent>/v1.md`), per-agent output schemas, guidance injection on re-runs, server-side enforcement of release-blocking rules, stub fallback without an API key | ✅ done |
| 4 | Frontend: React + Tailwind v4 dark mission-control UI — pipeline board (phase columns, agent progress dots, gate chips), story drawer (run cards with full HITL actions, re-run diff view, gate ceremony, timeline, details), Jira push queue with preview, filterable hash-chained audit view with export + live chain-verify, settings screen. Live WebSocket updates. | ✅ done (build clean, verified end-to-end) |
| 5 | Hardening: bounded free-text inputs, clean HTTP error mapping (404/409/422/502 + logged generic 500 that never leaks internals), gate sign-off committed before best-effort Jira pushes so it can't be lost, React error boundary, `.gitignore`, README + `.env.example` | ✅ done (53 tests passing) |

**All five build steps are complete.** 53 backend tests pass; the frontend builds clean (`tsc` + `vite`) and is verified end-to-end.

## Backend — quick start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # defaults are fine for demo mode
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Then seed the demo sprint (8 mock wealth-management stories, no Jira
credentials needed):

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/demo/seed
```

Interactive API docs: http://127.0.0.1:8000/docs

## Frontend — quick start

With the backend running on port 8000, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the printed URL (default http://localhost:5173). Vite proxies `/api`,
`/health` and `/ws` to the backend, so no CORS or env config is needed. Enter
your name in the header (every action is attributed), then **Sync from Jira**
or seed the demo sprint from the empty-board prompt.

The UI is dark-mode mission-control:

- **Pipeline board** — stories as cards across the four phase columns, each with
  agent progress dots (grey pending, amber awaiting approval, cyan running,
  violet awaiting your decision, green accepted, red rejected/failed) and a gate
  status chip. Badges for cloud, FCA impact, and the "Jira changed since last
  agent run" warning.
- **Story drawer** — Approve &amp; Run / Accept / Reject-with-reason / Re-run-with-
  guidance on each agent, structured output rendered per agent (INVEST scores,
  Gherkin blocks, integrity-check tables…), a diff view comparing re-run
  attempts, the four gates, and a full event timeline.
- **Gate sign-off ceremony** — evidence checklist, mandatory name/role/rationale,
  and a hard block (no override) when release-blocking findings are present.
- **Jira push queue** — preview exactly what will be posted, approve to send,
  retry failures.
- **Audit trail** — filterable append-only log, CSV/JSON export, and a live
  hash-chain verification badge.
- **Settings** — Jira project/JQL/sync and per-gate auto comment/label/transition.

`npm run build` runs `tsc -b` then `vite build` — a clean production build with
no type errors.

### Try the HITL flow via the API

1. `GET /api/v1/stories` — board payload; each story shows its proposed agent
   runs (first one `AWAITING_APPROVAL`, the rest `PROPOSED`) and four `LOCKED` gates.
2. `POST /api/v1/runs/{id}/approve` `{"approver": "Your Name"}` — Approve & Run.
3. `POST /api/v1/runs/{id}/accept` / `/reject` / `/rerun` — accept unlocks the
   next agent; re-run takes `guidance` injected into the agent's next prompt.
4. When all three phase agents are accepted, the phase gate becomes
   `READY_FOR_SIGNOFF`: `POST /api/v1/gates/{id}/signoff` with
   `approver_name`, `approver_role` and a typed `rationale` (all mandatory).
5. `GET /api/v1/audit` — filterable event log; `/api/v1/audit/export?format=csv`
   for compliance export; `/api/v1/audit/verify` re-derives the whole hash chain.

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

### Going live against real Jira

Set in `backend/.env`: `DEMO_MODE=false`, `JIRA_BASE_URL` (e.g.
`https://yourco.atlassian.net`), `JIRA_EMAIL`, `JIRA_API_TOKEN`. Then:

- `POST /api/v1/jira/test-connection` — verifies credentials (`/myself`).
- `GET/PUT /api/v1/settings` — project key, board id, JQL override, **field
  mappings** (story points, sprint, FCA-impact and Cloud custom field IDs,
  acceptance-criteria mode: custom field vs parsed from the description),
  per-gate auto-post/label/transition, sync interval. Secrets never live here.
- Pushes always render a preview first (`POST /api/v1/push/draft`), send only
  on human approval, and failed sends sit in a retry queue
  (`GET /api/v1/push?status=FAILED`, `POST /api/v1/push/{id}/retry`).
- Jira status transitions are resolved dynamically by name per issue — no
  hardcoded transition IDs.
- Scheduled background sync: enable via settings (`sync.enabled`,
  `sync.interval_minutes`).

## Configuration

All secrets live in `backend/.env` (see `.env.example`). `DEMO_MODE=true`
(default) uses the in-memory mock Jira adapter; set `DEMO_MODE=false` plus the
Jira credentials to use the real REST v3 adapter. SQLite is the v1 database;
the schema uses only portable types, so the Postgres swap is a `DATABASE_URL`
change (to `postgresql+asyncpg://…`) — the append-only audit triggers have a
documented Postgres equivalent in `app/database.py`.

Models: `claude-sonnet-4-6` for reasoning agents, `claude-haiku-4-5` for
lightweight classification — both configurable in `.env`.

## How the non-negotiables are enforced (server-side, not just UI)

| Rule | Enforcement |
|---|---|
| No agent starts without recorded human approval | Runs are proposed `AWAITING_APPROVAL`/`PROPOSED`; only `POST /runs/{id}/approve` with a named approver moves a run to `RUNNING`, and it is rejected (409) unless the run is `AWAITING_APPROVAL`. The approval is an audit event. |
| Strict, sequential gate order | A gate reaches `READY_FOR_SIGNOFF` only when every phase agent's latest run is `ACCEPTED`; sign-off re-verifies at commit time and advances exactly one phase. Skipping is impossible via the state machine (`app/services/workflow.py`). |
| FCA-scenario & financial-integrity failures are release-blocking | The engine forces `release_blocking=true`/`verdict=FAIL` after the model responds; the gate logic refuses to become ready while any accepted run is blocking. There is no override field in any request schema. |
| Append-only audit trail | No update/delete endpoints, no ORM mutation path, **and** DB triggers that abort UPDATE/DELETE. Events are hash-chained; `GET /audit/verify` re-derives the chain. |
| Every Claude call is logged | Each run records agent name, prompt version, model, token usage, and input/output hashes. |

## Role-based work queue ("My Work")

Pick your **role** in the header; the **My Work** tab (with a live count badge)
shows only what is waiting on that role, grouped and deep-linked so you can act
in one click. `GET /api/v1/work?role=<role>` powers it. Responsibility model:

| Role | Sees |
|---|---|
| Product Owner | Gate 1 (Refinement) and Gate 4 (Release) sign-offs |
| Tech Lead | Gate 2 (Development) sign-offs |
| QE Lead | Gate 1 & Gate 3 sign-offs, **plus** every agent run to approve/decide and every Jira push to approve/retry (the QE Lead operates the pipeline) |
| Business Stakeholder | Gate 4 (Release) sign-offs |
| Compliance Officer | Gate 4 sign-offs **only when the story's FCA impact is HIGH** (unclassified is treated as HIGH, precautionary) |

Clicking a gate item opens the story drawer straight into the sign-off ceremony;
a run item opens the agent-runs view; a push item jumps to the push queue. It is
a focused *view* — it does not restrict who may act (the board and push queue
still allow any named user to act).

## Testing

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q     # 60 tests
```

```powershell
cd frontend
npm run build                            # tsc typecheck + production build
```

## Troubleshooting

- **Frontend can't reach the API:** make sure the backend is running on port
  8000 first — Vite proxies `/api`, `/health`, `/ws` there.
- **`http://127.0.0.1:5173` refuses connection but `http://localhost:5173`
  works:** Vite may bind IPv6 (`::1`) only. Use the `localhost` URL Vite prints,
  or add `--host 127.0.0.1`.
- **Agents return `[engine stub]` output:** no `ANTHROPIC_API_KEY` is set — add
  it to `backend/.env` for real agent execution (demo mode works without it).
- **Port 8000 already in use:** another uvicorn is running; stop it or pass
  `--port`.

## Agent engine

Without `ANTHROPIC_API_KEY`, agents run as deterministic stubs (the full HITL
workflow still works — useful for demos). With a key set, each Approve & Run:

1. loads the agent's **versioned prompt file** (`backend/prompts/<agent>/vN.md`;
   the registry pins the version, so `prompt_version` in the audit trail always
   resolves to the exact text used),
2. calls Claude with **structured outputs** against the agent's Pydantic
   schema (`app/services/agents/output_schemas.py`) — responses are guaranteed
   schema-valid JSON,
3. injects any **re-run guidance** from the human reviewer into the prompt,
4. re-enforces the release-blocking rules **server-side**: a failed financial
   integrity check or an open FCA-scenario failure forces
   `release_blocking=true` / `verdict=FAIL` no matter what the model returned,
5. records agent name, prompt version, model, token usage and input/output
   hashes to the audit trail.

API failures mark the run `FAILED` (kept, auditable) and a re-run is offered.
