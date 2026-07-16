# Roadmap — AI Agentic QE Platform

Forward-looking ideas to extend the platform. Grouped by theme; each item has a
rough **value** and **effort** read. Nothing here is committed to a release yet —
this is the idea backlog we prioritise from.

Legend: 🟢 high value · 🟡 medium · ⚪ nice-to-have · (S/M/L) = effort.

---

## 1. Compliance as a first-class product
*Exploits the hash-chained audit trail and FCA context — our biggest differentiator.*

- ✅ **SHIPPED — Regulatory Evidence Pack** — one-click auditor-ready HTML
  document (`GET /stories/{id}/evidence-pack`, print-to-PDF): gate sign-offs,
  the AI-governance execution record (every agent run + prompt version + model +
  tokens + output hash), regulatory & financial evidence, release-health
  synthesis, and the verified hash-chain.
- 🟡 **Consumer Duty outcome mapping (M)** — tag stories against the four
  Consumer Duty outcomes and score coverage per release.
- 🟡 **Cryptographic sign-off (M)** — bind each gate sign-off to a signing key
  for true non-repudiation, layered on the existing hash chain.

## 2. Trustworthy agents
*Raises confidence in the agentic core — the "trust" in "AI That Tests. Humans Who Trust."*

- ✅ **SHIPPED — Cross-Agent Referee + Release Health Index** — a cross-cutting
  synthesis over all of a story's runs: a confidence-weighted health score + band,
  per-phase breakdown, and deterministic checks that flag contradictions *between*
  agents (e.g. GO recommended while Financial Integrity failed). `GET
  /stories/{id}/health`.
- ✅ **SHIPPED — Confidence + self-critique** — every agent emits
  `{level, rationale, caveats}` on the shared envelope; the "why you might override
  me" caveats support the HITL gates. *(Not yet: auto-routing low confidence to a
  human — see below.)*
- ✅ **SHIPPED — Human-feedback loop / agent-performance analytics** — mines the
  Accept / Reject / Re-run-with-guidance decisions into per-agent trust scores,
  override rates and reject reasons. `GET /insights/agents` + the Agent Insights
  tab. Tells us *which agents humans push back on*.

### 📌 PARKED — Agent eval harness + golden dataset (M–L)
*The measured-accuracy complement to the (shipped) feedback loop. Feedback tells
us whether humans agree; an eval harness tells us whether an agent is actually
**right** against an expert-labelled answer key — and catches regressions before
they ship.*

- **Golden dataset** — per-agent files of `{input, expected}` cases labelled by a
  compliance/QE expert (e.g. Financial Integrity: a £1.63-discrepancy artifact →
  expected `verdict FAIL`, `release_blocking true`, `variance 1.63`).
- **Eval harness** — a runner that executes each agent (the real Claude path) on
  its golden cases and grades the output: exact-match for structured fields,
  set-overlap for citations (e.g. FCA Handbook refs), and LLM-as-judge on a rubric
  for free-text rationale. Produces a per-agent, per-prompt-version accuracy
  scorecard over time.
- **Why:** makes prompt versioning (v1→v2→v3) *safe* — regressions fail red
  before shipping; and turns "the AI said so" into "measured at N% against an
  expert-labelled test set, re-verified on every change." Gate it in CI.
- **Cost:** the golden labelling is the real investment (a human defines "correct"
  for a few dozen cases per agent) — and that labelled set *is* the defensible
  asset. Start with **Financial Data Integrity** (deterministic, grades cleanly).
- **Also parked here:** *auto-route low-confidence outputs to a human* — use the
  shipped `confidence.level` to force a mandatory human review when LOW, rather
  than letting it flow through on Accept.

### 📌 PARKED — Meta-agents: agent health + memory (build in sequence)
*Agents about the agents. Note the overlap with what's already shipped, and the
FCA guardrail on "learning".*

**Already shipped (don't rebuild):** Cross-Agent Referee + Release Health Index
(per-story synthesis + contradictions); Agent-Performance / Feedback analytics
(`/insights/agents` — per-agent trust, accept/reject/rerun). Those cover *quality*
health. The two below are the gaps.

**1) Operational Agent Health monitor (M) — build first.**
The SRE/observability layer the quality analytics don't give: failure/error rates
(`RUN_FAILED`), latency, **token cost/budget**, per-model and **per-prompt-version
reliability** (did v3 regress?), confidence trend, and **anomaly alerts**
("Static Analysis started failing after the v3 prompt"). Deterministic **service +
dashboard** (like Insights) — cheap and reproducible; an LLM layer is only needed
later for narrative "why is it degrading" explanations. Design sketch was
`services/agent_health.py` → `GET /insights/agent-health` → an "Operational Health"
section on the Agent Insights tab.

**2) Institutional Memory — advisory briefing agent (L) — build second.**
Today every agent is **stateless** (no memory across stories). A Refinement-phase
**advisory briefing agent** would, at intake, recall relevant past
stories/decisions/outcomes and brief the team ("similar to WLTH-88, which failed
Financial Integrity on rounding; reusable BDD from WLTH-90"), backed by a memory
store. Scoped **advisory-only** (agreed):
- **Advisory** — surfaces context; the human still gates. No behaviour auto-change.
- **Transparent** — what it recalled and why is in the audit trail.
- **Reproducible** — a past decision replays with the memory it used.
- *Deferred (FCA landmine):* RAG knowledge reuse (retrieve past accepted BDD /
  reg-mappings / fixtures) and **any feedback-driven self-tuning** — the latter
  risks auditability/reproducibility and is cautioned against in a regulated context.

## 3. Proactive intelligence
*Activates the underused "P" (Proactive) in PACT.*

- 🟢 **Regulation-change → test-impact agent (L)** — monitor FCA Handbook /
  Consumer Duty updates and map changes to affected scenarios/stories.
- 🟡 **Org-drift detection (M)** — compare live Salesforce metadata to the tested
  baseline and auto-raise a story on drift.
- 🟡 **Predictive risk radar (M)** — learn from historical run outcomes to score
  which incoming stories are likely to fail testing.

## 4. Human-in-the-loop UX

- 🟢 **"Ask the audit trail" (M)** — natural-language Q&A (RAG over audit events +
  agent outputs): "Why was WLTH-101 blocked?" → sourced answer with links.
- 🟡 **Approval SLAs + escalation (S)** and **Slack/Teams notifications (S)** wired
  to the existing work queue.

## 5. Ecosystem depth

- 🟢 **Copado CI/CD integration** — see [COPADO-INTEGRATION.md](COPADO-INTEGRATION.md).
  - **Phase 1 (in progress): ingest-only** — Copado CodeScan/CRT/Apex/commit
    results normalise onto existing artifact kinds and feed the agents.
  - **Phase 2 (planned): gating** — "Copado holds, we release on sign-off"; prod
    promotion blocked until the human Release gate is signed off, no override.
- ⚪ **Synthetic FCA-safe test data (M)** — generate anonymised household/account
  fixtures so no real client data is used in testing.

## 6. New QE agents (Development & Testing phases)
*Under active discussion — candidate agents to fill coverage gaps. See notes as
we agree scope, then build following the plan → confirm → build rhythm.*

- **Development:** Unit Test Quality, Governor-Limit / Performance Risk,
  Security & Sharing (CRUD/FLS), Declarative-Change (Flow/Validation) review,
  Deployment/Package Readiness. *(shortlist — TBD)*
- **Testing:** Test Case / UAT Design, Integration & E2E Journey, Defect Triage /
  Root Cause, Accessibility (WCAG for client portals), Data Migration Validation.
  *(shortlist — TBD)*

## 7. Architecture & tech-debt improvements
*Architect's review output. Trajectory agreed: **demo / prototype / portfolio** —
so items are right-sized to demonstrate senior judgement, not gold-plated for a
live regulated deployment. Sequenced into reviewable batches, signal-first.
Nothing built yet.*

**Batch 1 — CI + cheap correctness (highest signal per hour)**
- 🟢 **GitHub Actions CI (S)** — pytest + `tsc`/`vite build` on every push; green
  badge on the README.
- 🟢 **Enforce signer roles at gate sign-off (S)** — reject a sign-off whose role
  isn't a permitted signer for the phase (`workflow.signoff_gate` + existing
  `GATE_SIGNERS`). Makes the HITL model actually enforced.
- 🟡 **`ARCHITECTURE.md` + ruff/eslint config (S)** — document the `.env`-vs-DB
  settings boundary and the (deferred) migration strategy.

**Batch 2 — Robustness (small, good hygiene)**
- 🟡 Retain raw Copado payload + payload size cap + a TestClient HTTP-level Copado test.
- 🟡 Artifact **dedupe/precedence** in `gather_for_agent` (newest-per-kind).
- ⚪ **Startup validation** of configured model IDs.

**Batch 3 — Refactors (craftsmanship)**
- 🟡 Split `demo_outputs.py` (1,506 lines) and `RunCard.tsx` (1,208) into per-agent
  modules/components.
- 🟡 Consolidate response models into `schemas/`; introduce a **declarative
  per-agent capability registry** (artifact kinds + upstream + blocking + prompt
  version in one place).
- ⚪ Frontend/backend type drift — document an OpenAPI→TS convention (codegen slimmed).

**Batch 4 — Auth seam (portfolio version, not real SSO)**
- 🟡 Introduce an **auth/identity dependency** resolving "current actor + roles"
  (stubbed for demo, pluggable for OIDC); derive `approver` from it instead of the
  request body. Demonstrates authN/authZ + non-repudiation without an IdP integration.

**Deliberately slimmed / deferred (portfolio scope):**
- ❌ Real SSO/OIDC integration — the seam (Batch 4) shows the judgement; full IdP
  wiring is effort no reviewer exercises.
- ⏸ Alembic migrations + Postgres append-only triggers — matter only for live
  deployment; documented in `ARCHITECTURE.md` instead. *(Optional showcase: add
  Alembic anyway, ~1h.)*

---

### Suggested starting order
1. **Regulatory Evidence Pack** — highest value-per-effort, makes the compliance
   story tangible.
2. **Cross-agent Referee** — directly strengthens trust in the agentic pipeline.
3. **Architecture Batch 1** (Section 7) — CI + role enforcement; credibility for
   little code, guards everything after.
4. Then Architecture Batches 2–4, new Development/Testing agents (Section 6), and
   Copado Phase 2 gating as scope is agreed.
