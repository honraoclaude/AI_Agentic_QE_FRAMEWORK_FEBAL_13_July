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

---

### Suggested starting order
1. **Regulatory Evidence Pack** — highest value-per-effort, makes the compliance
   story tangible.
2. **Cross-agent Referee** — directly strengthens trust in the agentic pipeline.
3. Then prioritise new Development/Testing agents (Section 6) once scope is agreed.
