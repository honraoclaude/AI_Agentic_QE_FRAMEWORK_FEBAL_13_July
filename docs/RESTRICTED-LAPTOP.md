# Running on a Restricted (No-Admin) Work Laptop

This guide sets up the platform on a locked-down Windows machine where you
**cannot install software as administrator**, but you **can** reach GitHub and
use `pip`/`npm`. It covers both demo mode (fully offline) and live mode
(real Claude API + Jira).

---

## What the machine actually needs

| Component | Needed for | Notes |
|---|---|---|
| Python 3.11+ + `pip` deps | Backend | Per-user install, no admin |
| Node.js + `npm` | Building/serving the frontend | Portable zip, no admin |
| Git (optional) | Cloning | Or download the repo ZIP instead |
| Outbound HTTPS to `api.anthropic.com` | **Live** agent mode | Firewall allowlist may be required |
| Outbound to your Jira host | **Live** Jira sync | Firewall allowlist may be required |

> **Demo mode (`DEMO_MODE=true`) needs no network and no API key.** Get it
> running in demo mode first, then switch to live mode.

---

## Step 0 — Install the toolchain (no admin)

- **Python 3.11+** — [python.org](https://www.python.org/downloads/) → Windows
  64-bit installer. Tick **"Add python.exe to PATH"**, choose **"Install Now"**
  (installs per-user to `%LOCALAPPDATA%\Programs\Python`). Do **not** select
  "Install for all users".
- **Node.js** — nodejs.org → **"Windows Binary (.zip)"**. Extract to e.g.
  `C:\Users\<you>\tools\node` and add that folder to your **user** PATH.
  `npm` is bundled.
- **Git** *(optional)* — [PortableGit](https://git-scm.com/download/win)
  ("64-bit Portable"). Or skip git entirely and download the repo ZIP (below).

Verify in a fresh PowerShell: `python --version`, `npm --version`.

---

## Step 1 — Get the code

**Option A — clone (if PortableGit is set up):**
```powershell
cd $HOME\projects
git clone https://github.com/honraoclaude/AI_Agentic_QE_FRAMEWORK_FEBAL_13_July.git
cd AI_Agentic_QE_FRAMEWORK_FEBAL_13_July
```

**Option B — download ZIP (no git needed):** On the GitHub repo page, click the
green **`< > Code`** button → **Download ZIP**. Extract it. This gives you every
tracked file with the correct folder structure in one action.

> **Do not copy files one-by-one from the GitHub web UI.** See
> [Manual copy](#appendix--manual-copy-if-you-must) for why, and what to skip if
> you have no other choice.

---

## Steps 2–3 — One-shot (recommended)

From the repo root, run the bundled bootstrap script. It checks for Python/npm,
creates the backend venv, installs backend + frontend dependencies, and seeds
`backend\.env` (in demo mode) if it's missing. Safe to re-run.

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Then skip to [Step 4](#step-4--configure-credentials). Prefer to do it by hand?
Use the manual steps below instead.

### Step 2 (manual) — Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Step 3 (manual) — Frontend

```powershell
cd ..\frontend
npm install
```

## Step 4 — Configure credentials

The repo ships `backend\.env.example` but **not** `.env` (gitignored).
Create `backend\.env`:

```
DEMO_MODE=false
ANTHROPIC_API_KEY=sk-ant-...
REASONING_MODEL=claude-sonnet-4-6
CLASSIFICATION_MODEL=claude-haiku-4-5
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...
JIRA_PROJECT_KEY=WLTH
JIRA_BOARD_ID=<your board id>
SYNC_ENABLED=true
SYNC_INTERVAL_MINUTES=15
```

Start with `DEMO_MODE=true` and no keys to confirm the app runs, then flip.

## Step 5 — Run (two terminals)

```powershell
# Terminal 1 — backend
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (dev server proxies /api and /ws to :8000)
cd frontend
npm run dev
```

Open **http://localhost:5173**. Backend health: **http://127.0.0.1:8000/health**.

---

## Restricted-network notes

**Proxy.** If your network uses a proxy, set it for the app at runtime too:
```powershell
$env:HTTPS_PROXY = "http://proxy.host:port"
$env:HTTP_PROXY  = "http://proxy.host:port"
# for git clones:
git config --global http.proxy http://proxy.host:port
```

**Firewall allowlisting.** Live mode needs outbound HTTPS to `api.anthropic.com`
and to your Jira host. `pip`/`npm` working does not guarantee these are open —
request them from IT if the app times out at runtime.

**Compliance (do this before live mode).** In live mode, real Jira story/AC text
is sent to the Anthropic API, and you store an API token + Jira credentials
locally. For an FCA-regulated context, confirm with security/compliance that:
- sending Jira content to Anthropic is covered (data-processing terms; no client
  PII in story text),
- storing secrets in a local `.env` meets policy (prefer pulling from a corporate
  secrets vault at runtime over a plaintext file),
- `api.anthropic.com` egress is sanctioned.

---

## Appendix — Manual copy (if you *must*)

Copying files individually from the GitHub web UI is **error-prone and not
recommended**: there are ~116 tracked files across nested folders, some are
binary (e.g. `package-lock.json`), and it's easy to miss files, flatten the
folder structure, or corrupt line endings. **Prefer Download ZIP (Step 1,
Option B)** — it is a single click and reproduces everything correctly.

If you genuinely cannot use clone or ZIP, copy these **folders** (preserving
structure), not just loose files:

**Copy (source — required):**
- `backend/app/**` (all Python source, nested packages)
- `backend/prompts/**` (all agent prompt versions)
- `backend/tests/**`
- `backend/requirements.txt`, `backend/pytest.ini`, `backend/.env.example`
- `frontend/src/**` (all `.tsx`/`.ts`/`.css`)
- `frontend/index.html`, `frontend/package.json`, `frontend/package-lock.json`
- `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/.gitignore`
- top level: `README.md`, `.gitignore`, this `docs/` folder

**Do NOT copy (generated or secret — recreated locally):**
- `backend/.venv/` — recreated by `python -m venv`
- `frontend/node_modules/` — recreated by `npm install`
- `frontend/dist/` — recreated by `npm run build`
- `backend/pact_qe.db` — the SQLite DB, regenerated on first run
- `backend/.env` — never exists in git; you create it fresh (secrets)
- `__pycache__/`, `*.pyc`, `*.log`

`package.json` + `package-lock.json` and `requirements.txt` are what let
`npm install` / `pip install` rebuild the dependency folders — so you never need
to copy `node_modules` or `.venv` themselves.
