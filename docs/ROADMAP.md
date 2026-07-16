# Roadmap — AI Agentic QE Platform

Forward-looking ideas to extend the platform. Grouped by theme; each item has a
rough **value** and **effort** read. Nothing here is committed to a release yet —
this is the idea backlog we prioritise from.

Legend: 🟢 high value · 🟡 medium · ⚪ nice-to-have · (S/M/L) = effort.

---

## 1. Compliance as a first-class product
*Exploits the hash-chained audit trail and FCA context — our biggest differentiator.*

- 🟢 **Regulatory Evidence Pack (S–M)** — one-click "Generate Audit Bundle": a
  timestamped PDF per release compiling gate sign-offs, every agent output +
  prompt version + token/hash, financial-integrity checks, and the verified
  audit chain. Turns 7-year retention into a 30-second deliverable.
- 🟡 **Consumer Duty outcome mapping (M)** — tag stories against the four
  Consumer Duty outcomes and score coverage per release.
- 🟡 **Cryptographic sign-off (M)** — bind each gate sign-off to a signing key
  for true non-repudiation, layered on the existing hash chain.

## 2. Trustworthy agents
*Raises confidence in the agentic core — the "trust" in "AI That Tests. Humans Who Trust."*

- 🟢 **Cross-agent Referee / consistency meta-agent (M)** — flags contradictions
  between agent outputs (e.g. BDD says covered, AC Compliance says not).
- 🟢 **Agent eval harness + golden dataset (M)** — labelled stories with known
  outputs, run on every prompt/model change, producing per-agent accuracy
  metrics over time. Converts "the AI said so" into measured, defensible quality.
- 🟡 **Confidence + self-critique (S)** — each agent emits a confidence score and
  a "why you might override me" note; low confidence auto-routes to a human.

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
