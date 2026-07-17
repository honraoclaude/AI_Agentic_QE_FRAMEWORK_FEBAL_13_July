# Severity & Priority — the one calibrated scale

Every agent uses **one** severity scale, so findings are comparable across the
whole pipeline and the Cross-Agent Referee can rank/aggregate them
(`severity_rank()` in `output_schemas.py`).

## Severity (ascending: LOW → BLOCKER)

| Level | Rank | Meaning / calibration |
|---|---|---|
| **LOW** | 1 | Cosmetic or stylistic; no functional/regulatory impact. A passing check. |
| **MEDIUM** | 2 | A real issue that should be fixed but does not endanger the release. |
| **HIGH** | 3 | Serious defect/finding; likely client-facing or a material quality risk. |
| **CRITICAL** | 4 | Severe — data/security/financial correctness at stake; fix before release. |
| **BLOCKER** | 5 | Stops the release. FCA-scenario or financial-integrity failure — no override. |

The former defect vocabulary (`MAJOR`/`MINOR`) is folded in: **MAJOR → HIGH**,
**MINOR → LOW**. `severity_rank()` still accepts them as legacy aliases.

## Priority (execution order — unchanged, already standard)

| Priority | Meaning |
|---|---|
| **P1** | Regulatory / financial / release-critical — do first. |
| **P2** | Core functionality. |
| **P3** | Edge / cosmetic. |

## Separate axes (deliberately *not* severity)

These measure a different thing and keep their own small scales:

- **Impact** (`LOW/MEDIUM/HIGH`) — e.g. a Deployment-Risk factor's blast size.
- **Risk status** (`OK/CONCERN/BLOCKER`) — a factor's state.
- **Gap severity** (`NONE/LOW/MEDIUM/HIGH`) — AC-Compliance, where `NONE` = no gap.
- **Confidence** (`HIGH/MEDIUM/LOW`) — the agent's self-assessed certainty.

## Where it's enforced
- `Severity` (and the `TestSeverity` alias) in
  [`output_schemas.py`](../backend/app/services/agents/output_schemas.py) — the
  single source of truth; structured outputs validate against it.
- `severity_rank()` is used by the Referee to compute the story's
  `worst_finding_severity` across all agents.
