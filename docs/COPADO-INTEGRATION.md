# Copado CI/CD Integration — Design

How the platform integrates with **Copado** (Salesforce DevOps). Copado stays the
pipeline; the framework is the quality-and-compliance brain that ingests Copado's
results as agent evidence and (Phase 2) gates promotions on recorded human
sign-off.

Chosen approach (agreed): **ingest-only first**, gate model
**"Copado holds, we release on sign-off"** for Phase 2.

---

## Two-way model

```
   Copado  ──(1) results as artifacts──▶  Framework agents  ──▶  verdicts + gate sign-off
 (pipeline)                                                              │
      ▲                                                                  │
      └───────────────(2) promotion allowed / blocked ──────────────────┘   (Phase 2)
```

## Phase ↔ Copado pipeline mapping

| Framework phase | Copado stage | Copado emits → artifact kind | Feeds agents |
|---|---|---|---|
| Development | Commit + validate | CodeScan → `SARIF`; Apex tests → `JUNIT`; committed files → `METADATA` | Static Analysis, Apex Coverage, AC Compliance |
| Testing | Deploy to UAT/QA | Robotic Testing (CRT) / Apex → `JUNIT`; recon → `FINANCIAL`; changed components → `METADATA` | Test Execution Analyst, Financial Integrity, Regression Scope |
| Release | Promote to Production | deployment/validation → `METADATA` | Release Readiness — Phase 2 gates the prod promotion |

**Key reuse:** Copado outputs normalise onto the platform's *existing* artifact
kinds, so no agent needs rewriting — they just gain a new feed. In particular a
Copado User Story's committed file list becomes the `METADATA` manifest that
already drives Regression Scope's `driving_components`.

---

## Phase 1 — Ingest-only (this build)

### Flow
```
Copado pipeline event (post-CodeScan / post-CRT / post-validate)
  └─ Copado Function/Webhook ──POST /api/v1/copado/results (shared-secret auth)──▶
       └─ resolve Copado User Story ─▶ Jira key ─▶ framework Story
            └─ normalise payload ─▶ existing ArtifactKind ─▶ stored as an Artifact
                 └─ existing agents consume it, unchanged; event ─▶ audit trail
```

### Components (mirror the `services/jira/` package)
- **`services/copado/normaliser.py`** — pure functions turning a Copado result
  payload into one of the existing normalised artifact shapes:
  - `codescan` → `SARIF` (SARIF doc passthrough, or Copado violations list)
  - `apex_tests` / `crt` → `JUNIT` (built directly from Copado test JSON)
  - `commit` → `METADATA` (component list)
- **`services/copado/fixtures.py`** — sample payloads for demo mode / the
  `/copado/simulate` endpoint, so the whole flow runs offline.
- **`services/copado/service.py`** — `ingest_result(...)`: resolve story,
  normalise, store as an artifact with `source="COPADO"` + `source_ref`
  (e.g. `US-1234 @ UAT`), audit as `ARTIFACT_INGESTED`.

### Storage / provenance
`Artifact` gains `source` (`MANUAL` | `COPADO`) and `source_ref`. The upload path
and the Copado path share one `store_artifact()` helper, so parsing/agent
consumption is identical regardless of origin.

### API (`/api/v1/copado`)
- `POST /copado/results` — the ingestion webhook Copado Functions call. Body:
  `{jira_key?, copado_user_story_id?, result_type, payload, run?}`. Authenticated
  with a shared secret (`X-Copado-Signature`) from `.env`
  (`COPADO_WEBHOOK_SECRET`); skipped in demo mode.
- `POST /copado/simulate` — **demo only**: inject sample results from fixtures so
  the flow is verifiable without a real Copado org.
- `GET /copado/status` — connection check.

### Config (`.env`)
`COPADO_BASE_URL`, `COPADO_API_TOKEN`, `COPADO_WEBHOOK_SECRET`, `COPADO_ENABLED`.
Secrets via `.env` only, never hardcoded.

### Linking
A result may carry `jira_key` and/or `copado_user_story_id`. On first sighting we
link them: a Story found by `jira_key` gets its `copado_user_story_id` recorded.

---

## Phase 2 — Gating (later)

Gate model **"Copado holds, we release on sign-off"**:
- A Copado Quality-Gate / manual step pauses the promotion and calls
  `POST /api/v1/copado/quality-gate`; the framework returns **hold**.
- When the human **Release gate sign-off** is recorded, a push-queue-style
  callback calls Copado's API to resume/approve the promotion.
- **Production cannot promote without the sign-off — no override.** FCA and
  financial-integrity blocking rules are unchanged.

This reuses the existing gate-signoff + push-queue machinery, so it is a natural
extension once ingest is proven.

---

## Non-negotiables preserved
- Every Copado event is written to the append-only, hash-chained audit trail.
- No agent runs without human approval; every phase ends in a gate sign-off.
- FCA-scenario and financial-integrity failures remain release-blocking.
- All secrets via `.env`.
