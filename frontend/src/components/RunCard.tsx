import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "../api";
import type { AgentDef, PushItem, ReplayReport, Run } from "../types";
import {
  Badge,
  Button,
  Field,
  fmtTime,
  inputCls,
  Modal,
  PactBadges,
  RUN_STATUS_META,
  useToast,
} from "../ui";

// ------------------------------------------------- generic output rendering

const ENVELOPE_KEYS = new Set([
  "agent",
  "agent_name",
  "pact",
  "verdict",
  "summary",
  "findings",
  "confidence",
  "release_blocking",
  "guidance_applied",
]);

const SEV_COLORS: Record<string, string> = {
  LOW: "text-ink-dim",
  MEDIUM: "text-warn",
  HIGH: "text-bad",
  CRITICAL: "text-bad font-bold",
  BLOCKER: "text-bad font-bold underline",
};

function ValueBlock({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined)
    return <span className="text-ink-faint">—</span>;
  if (typeof value === "boolean")
    return <span className={value ? "text-ok" : "text-ink-faint"}>{String(value)}</span>;
  if (typeof value === "number" || typeof value === "string")
    return <span className="whitespace-pre-wrap">{String(value)}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-faint">none</span>;
    // Gherkin scenarios get code blocks.
    if (value.every((v) => typeof v === "object" && v !== null && "gherkin" in v)) {
      const tagColor = (t: string): string => {
        if (t === "@fca" || t === "@p1" || t === "@negative") return "text-bad";
        if (t === "@manual" || t === "@p2" || t === "@edge") return "text-warn";
        if (t === "@automated" || t === "@positive") return "text-ok";
        if (t === "@non-functional") return "text-review";
        return "text-accent";
      };
      const prioCls: Record<string, string> = {
        P1: "border-bad/50 bg-bad/10 text-bad",
        P2: "border-warn/50 bg-warn/10 text-warn",
        P3: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2.5">
          {value.map((s, i) => {
            const sc = s as {
              title?: string;
              level?: string;
              category?: string;
              test_type?: string;
              priority?: string;
              automation?: { recommended?: boolean; framework?: string; reason?: string };
              tags?: string[];
              covers?: string[];
              ac_refs?: string[];
              example_refs?: string[];
              gherkin: string;
            };
            const auto = sc.automation;
            return (
              <div key={i}>
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                  {sc.priority && (
                    <Badge className={prioCls[sc.priority] ?? "border-line text-ink-dim"}>
                      {sc.priority}
                    </Badge>
                  )}
                  {(sc.ac_refs ?? []).map((r) => (
                    <Badge key={r} className="border-accent/40 bg-accent/10 text-accent">
                      {r}
                    </Badge>
                  ))}
                  {(sc.example_refs ?? []).map((r) => (
                    <span key={r} className="font-mono text-[10px] text-ink-faint">
                      {r}
                    </span>
                  ))}
                  {sc.level && (
                    <Badge className="border-line text-ink-dim">{sc.level}</Badge>
                  )}
                  {sc.category && (
                    <Badge className="border-line text-ink-dim">
                      {sc.category.toLowerCase()}
                    </Badge>
                  )}
                  {auto && (
                    <span
                      title={auto.reason}
                      className={`text-[10px] ${auto.recommended ? "text-ok" : "text-warn"}`}
                    >
                      {auto.recommended ? `🤖 ${auto.framework}` : "✋ Manual"}
                    </span>
                  )}
                  <span className="text-ink">{sc.title}</span>
                </div>
                {(sc.tags ?? []).length > 0 && (
                  <div className="mb-1 flex flex-wrap gap-1.5">
                    {(sc.tags ?? []).map((t) => (
                      <span key={t} className={`font-mono text-[10px] ${tagColor(t)}`}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                <pre className="overflow-x-auto rounded border border-line bg-bg p-2 font-mono text-[11px] leading-relaxed text-ink">
                  {sc.gherkin}
                </pre>
                {auto?.reason && (
                  <p className="mt-0.5 text-[10px] text-ink-faint">
                    automation: {auto.reason}
                  </p>
                )}
                {(sc.covers ?? []).length > 0 && (
                  <p className="mt-0.5 text-[10px] text-ink-faint">
                    covers: {(sc.covers ?? []).join("; ")}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      );
    }
    // AC Compliance traceability matrix: status-coloured criterion cards.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "criterion" in v && "status" in v,
      )
    ) {
      const statusCls: Record<string, string> = {
        COVERED: "border-ok/50 bg-ok/10 text-ok",
        PARTIAL: "border-warn/50 bg-warn/10 text-warn",
        NOT_COVERED: "border-bad/50 bg-bad/10 text-bad",
        NOT_VERIFIABLE: "border-line bg-panel-2 text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const m = v as {
              ac_id?: string;
              criterion: string;
              status: string;
              components?: string[];
              evidence?: string;
              fca_relevant?: boolean;
              severity?: string;
              test_coverage?: { has_scenario?: boolean; scenarios?: string[] };
              remediation?: string;
            };
            const tc = m.test_coverage;
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  {m.ac_id && (
                    <Badge className="border-accent/40 bg-accent/10 text-accent">
                      {m.ac_id}
                    </Badge>
                  )}
                  <Badge className={statusCls[m.status] ?? "border-line text-ink-dim"}>
                    {m.status.replace("_", " ").toLowerCase()}
                  </Badge>
                  {m.fca_relevant && (
                    <Badge className="border-bad/50 bg-bad/10 text-bad">FCA</Badge>
                  )}
                  {m.severity && m.severity !== "NONE" && (
                    <span className="font-mono text-[10px] text-ink-faint">
                      sev {m.severity}
                    </span>
                  )}
                  <span
                    title={tc?.scenarios?.join("; ")}
                    className={`ml-auto text-[10px] ${tc?.has_scenario ? "text-ok" : "text-warn"}`}
                  >
                    {tc?.has_scenario ? `✓ ${tc.scenarios?.length} scenario(s)` : "no test"}
                  </span>
                </div>
                <p className="text-[11px] text-ink">{m.criterion}</p>
                {m.evidence && (
                  <p className="mt-0.5 text-[10px] text-ink-dim">{m.evidence}</p>
                )}
                {(m.components ?? []).length > 0 && (
                  <p className="mt-0.5 font-mono text-[10px] text-accent">
                    {(m.components ?? []).join(", ")}
                  </p>
                )}
                {m.remediation && (
                  <p className="mt-0.5 text-[10px] text-warn">→ {m.remediation}</p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Test-failure triage: classification/severity/flaky chips, action, defect.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "test_name" in v &&
          "classification" in v &&
          "severity" in v,
      )
    ) {
      const clsCls: Record<string, string> = {
        PRODUCT_DEFECT: "border-bad/50 bg-bad/10 text-bad",
        TEST_DEFECT: "border-warn/50 bg-warn/10 text-warn",
        ENVIRONMENT: "border-review/50 bg-review/10 text-review",
        DATA: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const f = v as {
              test_name: string;
              classification: string;
              severity?: string;
              priority?: string;
              is_fca_scenario?: boolean;
              bdd_scenario?: string | null;
              likely_flaky?: boolean;
              rerun_recommended?: boolean;
              detail?: string;
              suggested_action?: string;
              suggested_defect?: { title?: string; component?: string } | null;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <Badge className={clsCls[f.classification] ?? "border-line text-ink-dim"}>
                    {f.classification.replace("_", " ").toLowerCase()}
                  </Badge>
                  {f.severity && (
                    <span
                      className={`font-mono text-[10px] ${f.severity === "BLOCKER" ? "text-bad" : "text-ink-faint"}`}
                    >
                      {f.severity}
                    </span>
                  )}
                  {f.priority && (
                    <span className="font-mono text-[10px] text-ink-faint">{f.priority}</span>
                  )}
                  {f.is_fca_scenario && (
                    <Badge className="border-bad/60 bg-bad/15 text-bad">FCA</Badge>
                  )}
                  {f.likely_flaky && <span className="text-[10px] text-warn">flaky</span>}
                  <span className="text-ink">{f.test_name}</span>
                </div>
                {f.detail && <p className="mt-0.5 text-[10px] text-ink-dim">{f.detail}</p>}
                {f.suggested_action && (
                  <p className="mt-0.5 text-[10px] text-ok">→ {f.suggested_action}</p>
                )}
                {f.bdd_scenario && (
                  <p className="text-[10px] text-review">↑ BDD: {f.bdd_scenario}</p>
                )}
                {f.suggested_defect?.title && (
                  <p className="text-[10px] text-bad">
                    defect: {f.suggested_defect.title} ({f.suggested_defect.component})
                  </p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Static-analysis issues: severity/category/source chips, CWE, remediation.
    if (
      value.every(
        (v) =>
          typeof v === "object" && v !== null && "rule" in v && "source" in v && "category" in v,
      )
    ) {
      const sevCls: Record<string, string> = {
        BLOCKER: "border-bad/70 bg-bad/20 text-bad font-bold",
        CRITICAL: "border-bad/60 bg-bad/15 text-bad",
        HIGH: "border-bad/50 bg-bad/10 text-bad",
        MEDIUM: "border-warn/50 bg-warn/10 text-warn",
        LOW: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const it = v as {
              rule: string;
              severity: string;
              category: string;
              source: string;
              location?: string;
              detail?: string;
              remediation?: string;
              confidence?: string;
              fsc_specific?: boolean;
              standard?: { cwe?: string; owasp?: string } | null;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <Badge className={sevCls[it.severity] ?? "border-line text-ink-dim"}>
                    {it.severity}
                  </Badge>
                  <Badge className="border-line text-ink-dim">
                    {it.category.replaceAll("_", " ").toLowerCase()}
                  </Badge>
                  <span
                    className={`text-[10px] ${it.source === "AI_AUGMENT" ? "text-review" : "text-ink-faint"}`}
                  >
                    {it.source === "AI_AUGMENT" ? "AI review" : "scanner"}
                  </span>
                  <span className="font-mono text-[11px] text-ink">{it.rule}</span>
                  {it.standard?.cwe && (
                    <span
                      title={it.standard.owasp}
                      className="font-mono text-[10px] text-accent"
                    >
                      {it.standard.cwe}
                    </span>
                  )}
                  {it.confidence && (
                    <span className="ml-auto text-[10px] text-ink-faint">
                      conf {it.confidence}
                    </span>
                  )}
                </div>
                {it.location && (
                  <p className="mt-0.5 font-mono text-[10px] text-ink-faint">{it.location}</p>
                )}
                {it.detail && <p className="mt-0.5 text-[10px] text-ink-dim">{it.detail}</p>}
                {it.remediation && (
                  <p className="mt-0.5 text-[10px] text-ok">→ {it.remediation}</p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Financial integrity checks: pass/fail, variance vs tolerance, materiality.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "within_tolerance" in v &&
          "expected" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const c = v as {
              name: string;
              category?: string;
              expected?: string;
              actual?: string;
              variance?: string;
              tolerance?: string;
              passed?: boolean;
              materiality?: string;
              severity?: string;
              regulatory_basis?: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className={c.passed ? "text-ok" : "text-bad"}>
                    {c.passed ? "✓" : "✗"}
                  </span>
                  {c.category && (
                    <Badge className="border-line text-ink-dim">
                      {c.category.toLowerCase()}
                    </Badge>
                  )}
                  <span className="text-ink">{c.name}</span>
                  {c.severity === "BLOCKER" && (
                    <Badge className="border-bad/60 bg-bad/15 text-bad">blocker</Badge>
                  )}
                </div>
                <div className="mt-0.5 font-mono text-[10px] text-ink-dim">
                  expected {c.expected} · actual {c.actual} · variance {c.variance} (tol{" "}
                  {c.tolerance})
                </div>
                {c.materiality && c.materiality !== "none" && (
                  <p className="text-[10px] text-warn">materiality: {c.materiality}</p>
                )}
                {c.regulatory_basis && (
                  <p className="text-[10px] text-ink-faint">{c.regulatory_basis}</p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Regression areas: cloud/priority/dependency, driving components, suite.
    if (
      value.every(
        (v) =>
          typeof v === "object" && v !== null && "dependency_type" in v && "cloud" in v,
      )
    ) {
      const prioCls: Record<string, string> = {
        HIGH: "border-bad/50 bg-bad/10 text-bad",
        MEDIUM: "border-warn/50 bg-warn/10 text-warn",
        LOW: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const a = v as {
              cloud: string;
              area: string;
              driving_components?: string[];
              dependency_type?: string;
              reason?: string;
              priority?: string;
              effort?: string;
              suggested_tests?: string[];
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  {a.priority && (
                    <Badge className={prioCls[a.priority] ?? "border-line text-ink-dim"}>
                      {a.priority}
                    </Badge>
                  )}
                  <Badge className="border-line text-ink-dim">{a.cloud}</Badge>
                  <span className="text-ink">{a.area}</span>
                  {a.effort && (
                    <span className="ml-auto font-mono text-[10px] text-ink-faint">
                      {a.effort}
                    </span>
                  )}
                </div>
                {a.reason && <p className="mt-0.5 text-[10px] text-ink-dim">{a.reason}</p>}
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
                  {a.dependency_type && (
                    <span className="text-review">
                      {a.dependency_type.replaceAll("_", " ").toLowerCase()}
                    </span>
                  )}
                  {(a.driving_components ?? []).map((c, j) => (
                    <span key={j} className="font-mono text-accent">
                      {c}
                    </span>
                  ))}
                </div>
                {(a.suggested_tests ?? []).length > 0 && (
                  <p className="mt-0.5 text-[10px] text-ink-faint">
                    run: {(a.suggested_tests ?? []).join("; ")}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Apex per-class coverage: name, coverage bar, threshold/assertion/gaps.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "class_name" in v &&
          "coverage_percent" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const c = v as {
              class_name: string;
              coverage_percent: number;
              meets_threshold?: boolean;
              financial_critical?: boolean;
              assertion_risk?: string;
              has_bulk_test?: boolean;
              has_negative_test?: boolean;
              gaps?: Array<{ type: string; area: string; risk: string }>;
            };
            const pct = c.coverage_percent;
            const bar = c.meets_threshold ? "bg-ok" : pct >= 75 ? "bg-warn" : "bg-bad";
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-ink">{c.class_name}</span>
                  {c.financial_critical && (
                    <Badge className="border-bad/50 bg-bad/10 text-bad">financial</Badge>
                  )}
                  {c.assertion_risk && c.assertion_risk !== "NONE" && (
                    <span
                      className={`text-[10px] ${c.assertion_risk === "HIGH" ? "text-bad" : "text-warn"}`}
                    >
                      assertions {c.assertion_risk}
                    </span>
                  )}
                  <span
                    className={`ml-auto font-mono text-[11px] ${c.meets_threshold ? "text-ok" : "text-bad"}`}
                  >
                    {pct}%
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-panel-2">
                  <div className={`h-full ${bar}`} style={{ width: `${Math.min(100, pct)}%` }} />
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className={c.has_bulk_test ? "text-ok" : "text-ink-faint"}>
                    {c.has_bulk_test ? "✓ bulk" : "✗ bulk"}
                  </span>
                  <span className={c.has_negative_test ? "text-ok" : "text-ink-faint"}>
                    {c.has_negative_test ? "✓ negative" : "✗ negative"}
                  </span>
                  {(c.gaps ?? []).map((g, j) => (
                    <span key={j} title={`${g.area} (${g.risk})`} className="font-mono text-warn">
                      {g.type}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    // Drafted Apex tests: priority/category chips, gap + BDD traceability.
    if (
      value.every(
        (v) =>
          typeof v === "object" && v !== null && "test_method" in v && "closes_gaps" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-1.5">
          {value.map((v, i) => {
            const t = v as {
              test_class_name?: string;
              test_method?: string;
              category?: string;
              priority?: string;
              closes_gaps?: string[];
              from_bdd_scenario?: string | null;
              outline?: string;
              test_data?: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  {t.priority && (
                    <Badge
                      className={
                        t.priority === "P1"
                          ? "border-bad/50 bg-bad/10 text-bad"
                          : "border-warn/50 bg-warn/10 text-warn"
                      }
                    >
                      {t.priority}
                    </Badge>
                  )}
                  {t.category && (
                    <Badge className="border-line text-ink-dim">
                      {t.category.toLowerCase()}
                    </Badge>
                  )}
                  <span className="font-mono text-accent">
                    {t.test_class_name}.{t.test_method}
                  </span>
                </div>
                {t.outline && <p className="mt-0.5 text-[10px] text-ink-dim">{t.outline}</p>}
                {(t.closes_gaps ?? []).length > 0 && (
                  <p className="mt-0.5 text-[10px] text-ink-faint">
                    closes: {(t.closes_gaps ?? []).join("; ")}
                  </p>
                )}
                {t.from_bdd_scenario && (
                  <p className="text-[10px] text-review">↑ from BDD: {t.from_bdd_scenario}</p>
                )}
                {t.test_data && (
                  <p className="text-[10px] text-ink-faint">data: {t.test_data}</p>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Deployment risk factors.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "factor" in v && "impact" in v && "status" in v,
      )
    ) {
      const stCls: Record<string, string> = {
        OK: "border-ok/50 bg-ok/10 text-ok",
        CONCERN: "border-warn/50 bg-warn/10 text-warn",
        BLOCKER: "border-bad/50 bg-bad/10 text-bad",
      };
      return (
        <div className="flex flex-col gap-1.5">
          {value.map((v, i) => {
            const f = v as { factor: string; impact: string; status: string; note: string };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                  <Badge className={stCls[f.status] ?? "border-line text-ink-dim"}>{f.status}</Badge>
                  <span className="text-[11px] font-medium text-ink">{f.factor}</span>
                  <span className="font-mono text-[10px] text-ink-faint">impact {f.impact}</span>
                </div>
                <div className="text-[10px] text-ink-dim">{f.note}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // Post-deploy verification checks.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "category" in v &&
          "target" in v &&
          "expected_result" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-1.5">
          {value.map((v, i) => {
            const c = v as {
              name: string; category: string; target: string;
              expected_result: string; priority: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                  <Badge className="border-line text-ink-dim">{c.priority}</Badge>
                  <span className="font-mono text-[10px] text-accent">{c.category.toLowerCase()}</span>
                  <span className="text-[11px] font-medium text-ink">{c.name}</span>
                </div>
                <div className="text-[10px] text-ink-dim">
                  <span className="text-ink-faint">{c.target}:</span> {c.expected_result}
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    // Integration & E2E journeys: cross-cloud journeys with status.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "clouds" in v &&
          "integration_points" in v &&
          "status" in v,
      )
    ) {
      const stCls: Record<string, string> = {
        PASS: "border-ok/50 bg-ok/10 text-ok",
        FAIL: "border-bad/50 bg-bad/10 text-bad",
        BLOCKED: "border-warn/50 bg-warn/10 text-warn",
        NOT_RUN: "border-line text-ink-faint",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const j = v as {
              name: string; clouds: string[]; steps: string[];
              integration_points: string[]; status: string; risk: string; notes?: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Badge className={stCls[j.status] ?? "border-line text-ink-dim"}>{j.status}</Badge>
                  <span className="text-[11px] font-medium text-ink">{j.name}</span>
                  {(j.clouds ?? []).map((c) => (
                    <span key={c} className="font-mono text-[10px] text-accent">{c}</span>
                  ))}
                </div>
                <div className="text-[10px] text-ink-faint">
                  seams: {(j.integration_points ?? []).join(" · ")}
                </div>
                {j.notes && <div className="mt-0.5 text-[10px] text-ink-dim">{j.notes}</div>}
              </div>
            );
          })}
        </div>
      );
    }

    // Security DAST findings.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "endpoint" in v && "owasp" in v && "evidence" in v,
      )
    ) {
      const sevCls: Record<string, string> = {
        BLOCKER: "border-bad/70 bg-bad/20 text-bad font-bold",
        CRITICAL: "border-bad/50 bg-bad/10 text-bad",
        HIGH: "border-bad/50 bg-bad/10 text-bad",
        MEDIUM: "border-warn/50 bg-warn/10 text-warn",
        LOW: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const f = v as {
              name: string; severity: string; endpoint: string; owasp: string;
              cwe?: string | null; evidence: string; remediation: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Badge className={sevCls[f.severity] ?? "border-line text-ink-dim"}>{f.severity}</Badge>
                  <span className="text-[11px] font-medium text-ink">{f.name}</span>
                  <span className="font-mono text-[10px] text-accent">{f.owasp}</span>
                  {f.cwe && <span className="font-mono text-[10px] text-ink-faint">{f.cwe}</span>}
                </div>
                <div className="font-mono text-[10px] text-ink-faint">{f.endpoint}</div>
                <div className="text-[11px] text-ink-dim">{f.evidence}</div>
                <div className="mt-0.5 text-[10px] text-ok">▸ {f.remediation}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // Defect triage clusters.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "signature" in v &&
          "classification" in v &&
          "suspected_root_cause" in v,
      )
    ) {
      const clsCls: Record<string, string> = {
        PRODUCT_DEFECT: "border-bad/50 bg-bad/10 text-bad",
        TEST_DEFECT: "border-warn/50 bg-warn/10 text-warn",
        ENVIRONMENT: "border-line text-ink-dim",
        DATA: "border-line text-ink-dim",
        FLAKY: "border-review/50 text-review",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const c = v as {
              signature: string; tests: string[]; classification: string;
              suspected_root_cause: string; suspected_component: string; severity: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Badge className={clsCls[c.classification] ?? "border-line text-ink-dim"}>
                    {c.classification.replaceAll("_", " ").toLowerCase()}
                  </Badge>
                  <Badge className="border-line text-ink-dim">{c.severity}</Badge>
                  <span className="font-mono text-[10px] text-ink">{(c.tests ?? []).length} test(s)</span>
                </div>
                <div className="font-mono text-[10px] text-bad">{c.signature}</div>
                <div className="text-[11px] text-ink-dim">
                  {c.suspected_root_cause} <span className="text-ink-faint">({c.suspected_component})</span>
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    // Automated Code Review: categorised review comments with suggestions.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "category" in v &&
          "suggestion" in v &&
          "comment" in v,
      )
    ) {
      const sevCls: Record<string, string> = {
        BLOCKER: "border-bad/70 bg-bad/20 text-bad font-bold",
        CRITICAL: "border-bad/50 bg-bad/10 text-bad",
        HIGH: "border-bad/50 bg-bad/10 text-bad",
        MEDIUM: "border-warn/50 bg-warn/10 text-warn",
        LOW: "border-line text-ink-dim",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const c = v as {
              file: string;
              line?: number | null;
              category: string;
              severity: string;
              comment: string;
              suggestion: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Badge className={sevCls[c.severity] ?? "border-line text-ink-dim"}>
                    {c.severity}
                  </Badge>
                  <span className="font-mono text-[10px] text-ink-faint">
                    {c.category.replaceAll("_", " ").toLowerCase()}
                  </span>
                  <span className="font-mono text-[10px] text-accent">
                    {c.file}
                    {c.line ? `:${c.line}` : ""}
                  </span>
                </div>
                <div className="text-[11px] text-ink">{c.comment}</div>
                <div className="mt-0.5 text-[10px] text-ok">▸ {c.suggestion}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // Deployability Validation: per-component deploy errors.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "component" in v && "problem" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-1.5">
          {value.map((v, i) => {
            const e = v as {
              component: string;
              component_type: string;
              problem: string;
              line?: number | null;
            };
            return (
              <div key={i} className="rounded border border-bad/40 bg-bad/5 p-2">
                <div className="mb-0.5 flex items-center gap-1.5">
                  <span className="font-mono text-[11px] text-bad">{e.component}</span>
                  <span className="font-mono text-[10px] text-ink-faint">
                    {e.component_type}
                    {e.line ? `:${e.line}` : ""}
                  </span>
                </div>
                <div className="text-[11px] text-ink-dim">{e.problem}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // FCA Regulatory Impact: applicable Handbook obligations.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "handbook_ref" in v && "area" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const r = v as {
              handbook_ref: string;
              area: string;
              obligation: string;
              relevance: string;
              triggered_by?: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex items-center gap-1.5">
                  <Badge className="border-accent/40 bg-accent/10 text-accent">
                    {r.handbook_ref}
                  </Badge>
                  <span className="font-mono text-[10px] text-ink-faint">{r.area}</span>
                  {r.triggered_by && (
                    <Badge className="ml-auto border-line text-ink-dim">
                      ⇠ {r.triggered_by}
                    </Badge>
                  )}
                </div>
                <div className="text-[11px] text-ink">{r.obligation}</div>
                <div className="mt-0.5 text-[10px] text-ink-dim">{r.relevance}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // Consumer Duty: the four outcomes with RAG status.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "outcome" in v &&
          "status" in v &&
          "assessment" in v,
      )
    ) {
      const statusCls: Record<string, string> = {
        ADDRESSED: "border-ok/50 bg-ok/10 text-ok",
        PARTIAL: "border-warn/50 bg-warn/10 text-warn",
        NOT_ADDRESSED: "border-bad/50 bg-bad/10 text-bad",
        NOT_APPLICABLE: "border-line text-ink-faint",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const o = v as {
              outcome: string;
              status: string;
              assessment: string;
              foreseeable_harm?: string | null;
              gap?: string | null;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex items-center gap-1.5">
                  <Badge className={statusCls[o.status] ?? "border-line text-ink-dim"}>
                    {o.status.replaceAll("_", " ")}
                  </Badge>
                  <span className="text-[11px] font-medium text-ink">
                    {o.outcome.replaceAll("_", " ").toLowerCase()}
                  </span>
                </div>
                <div className="text-[11px] text-ink-dim">{o.assessment}</div>
                {o.foreseeable_harm && (
                  <div className="mt-0.5 text-[10px] text-bad">⚠ {o.foreseeable_harm}</div>
                )}
                {o.gap && <div className="mt-0.5 text-[10px] text-warn">Gap: {o.gap}</div>}
              </div>
            );
          })}
        </div>
      );
    }

    // Compliance-by-Design: suggested acceptance criteria.
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v !== null &&
          "criterion" in v &&
          "regulatory_basis" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const c = v as {
              criterion: string;
              category: string;
              regulatory_basis: string;
              priority: string;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Badge
                    className={
                      c.priority === "MUST"
                        ? "border-bad/50 bg-bad/10 text-bad"
                        : "border-line text-ink-dim"
                    }
                  >
                    {c.priority}
                  </Badge>
                  <span className="font-mono text-[10px] text-ink-faint">
                    {c.category.replaceAll("_", " ").toLowerCase()}
                  </span>
                  <span className="font-mono text-[10px] text-accent">
                    {c.regulatory_basis}
                  </span>
                </div>
                <div className="text-[11px] text-ink">{c.criterion}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // Example Mapping: rule cards (AC-anchored) each with typed example cards.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "rule" in v && "examples" in v,
      )
    ) {
      const KIND_CLS: Record<string, string> = {
        HAPPY: "text-ok",
        NEGATIVE: "text-warn",
        BOUNDARY: "text-accent",
      };
      return (
        <div className="flex flex-col gap-2">
          {value.map((v, i) => {
            const em = v as {
              rule: string;
              ac_refs?: string[];
              examples: Array<
                string | { id?: string; text: string; kind?: string; fca?: boolean }
              >;
            };
            return (
              <div key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink">
                  <span className="text-accent">▸</span>
                  {em.rule}
                  {(em.ac_refs ?? []).map((r) => (
                    <Badge key={r} className="border-accent/50 bg-accent/10 text-accent">
                      {r}
                    </Badge>
                  ))}
                </div>
                <ul className="ml-3 space-y-0.5 text-[11px] text-ink-dim">
                  {(em.examples ?? []).map((ex, j) => {
                    if (typeof ex === "string")
                      return (
                        <li key={j} className="list-inside list-disc">
                          {ex}
                        </li>
                      );
                    return (
                      <li key={j} className="flex flex-wrap items-center gap-1.5">
                        {ex.id && (
                          <span className="font-mono text-[10px] text-ink-faint">
                            {ex.id}
                          </span>
                        )}
                        {ex.kind && (
                          <span
                            className={`font-mono text-[10px] ${KIND_CLS[ex.kind] ?? "text-ink-faint"}`}
                          >
                            {ex.kind.toLowerCase()}
                          </span>
                        )}
                        {ex.fca && (
                          <Badge className="border-bad/50 bg-bad/10 text-bad">FCA</Badge>
                        )}
                        <span>{ex.text}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      );
    }

    // Definition of Done: checkable contract — each item mapped to its verifier.
    if (
      value.every(
        (v) => typeof v === "object" && v !== null && "item" in v && "verified_by" in v,
      )
    ) {
      return (
        <div className="flex flex-col gap-1">
          {value.map((v, i) => {
            const d = v as { item: string; verified_by: string; fca_evidence?: boolean };
            const manual = !d.verified_by || d.verified_by === "MANUAL";
            return (
              <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="text-ink">{d.item}</span>
                {d.fca_evidence && (
                  <Badge className="border-bad/50 bg-bad/10 text-bad">FCA</Badge>
                )}
                <span
                  className={`font-mono text-[10px] ${manual ? "text-ink-faint" : "text-accent"}`}
                >
                  ✓ {manual ? "manual" : d.verified_by.replaceAll("_", " ")}
                </span>
              </div>
            );
          })}
        </div>
      );
    }

    // Agreements: decision-records with the audit "why".
    if (
      value.every((v) => typeof v === "object" && v !== null && "decision" in v)
    ) {
      return (
        <div className="flex flex-col gap-1.5">
          {value.map((v, i) => {
            const a = v as { decision: string; rationale?: string };
            return (
              <div key={i} className="text-[11px]">
                <div className="text-ink">{a.decision}</div>
                {a.rationale && (
                  <div className="ml-3 text-[10px] italic text-ink-faint">
                    why: {a.rationale}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // Open questions: owned + blocking-aware.
    if (
      value.every((v) => typeof v === "object" && v !== null && "question" in v)
    ) {
      return (
        <div className="flex flex-col gap-1">
          {value.map((v, i) => {
            const q = v as {
              question: string;
              owner_persona?: string;
              blocking?: boolean;
            };
            return (
              <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                {q.blocking && (
                  <Badge className="border-bad/70 bg-bad/20 font-bold text-bad">
                    BLOCKING
                  </Badge>
                )}
                <span className="text-ink">{q.question}</span>
                {q.owner_persona && (
                  <span className="font-mono text-[10px] text-ink-faint">
                    → {q.owner_persona.replaceAll("_", " ").toLowerCase()}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      );
    }
    if (value.every((v) => typeof v === "string")) {
      return (
        <ul className="list-inside list-disc space-y-0.5">
          {value.map((v, i) => (
            <li key={i} className="text-ink">
              {v as string}
            </li>
          ))}
        </ul>
      );
    }
    if (value.every((v) => typeof v === "object" && v !== null)) {
      const cols = Array.from(
        new Set(value.flatMap((v) => Object.keys(v as object))),
      );
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-line text-ink-faint">
                {cols.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">
                    {c.replaceAll("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((row, i) => (
                <tr key={i} className="border-b border-line/50 align-top">
                  {cols.map((c) => {
                    const cell = (row as Record<string, unknown>)[c];
                    return (
                      <td key={c} className="py-1 pr-3">
                        <ValueBlock value={cell} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
  }

  if (typeof value === "object") {
    return (
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-ink-faint">{k.replaceAll("_", " ")}</span>
            <span>
              <ValueBlock value={v} />
            </span>
          </div>
        ))}
      </div>
    );
  }
  return <span>{JSON.stringify(value)}</span>;
}

function InputPanel({ input }: { input: Record<string, unknown> }) {
  const story = (input.story ?? {}) as Record<string, unknown>;
  const ac = (story.acceptance_criteria ?? []) as string[];
  const rendered = input.rendered_prompt as string | undefined;
  const artifacts = (input.artifacts ?? []) as Array<{
    kind: string;
    filename: string;
    summary: string;
  }>;
  const upstream = (input.upstream ?? []) as Array<{
    agent_key: string;
    agent_name: string;
  }>;
  const metaKeys: [string, unknown][] = [
    ["FCA impact", story.fca_impact],
    ["Cloud", story.cloud],
    ["Story points", story.story_points],
    ["Sprint", story.sprint],
    ["Priority", story.priority],
    ["Phase", story.current_phase],
  ];
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-ink-faint">
        <span>agent {String(input.agent ?? "")}</span>
        <span>prompt {String(input.prompt_version ?? "")}</span>
        <span>attempt {String(input.attempt ?? "")}</span>
        <span>role {String(input.model_role ?? "")}</span>
      </div>

      {typeof input.guidance === "string" && input.guidance && (
        <div className="rounded border border-review/40 bg-review/10 px-2 py-1.5 text-review">
          Reviewer guidance injected: “{input.guidance}”
        </div>
      )}

      <div>
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Story context sent to the agent
        </h4>
        <div className="rounded border border-line bg-bg/50 p-2.5">
          <div className="mb-1 font-mono text-[11px] text-accent">
            {String(story.jira_key ?? "")}
          </div>
          <p className="mb-2 text-ink">{String(story.summary ?? "")}</p>
          {typeof story.description === "string" && story.description && (
            <p className="mb-2 whitespace-pre-wrap leading-relaxed text-ink-dim">
              {story.description}
            </p>
          )}
          {ac.length > 0 && (
            <div className="mb-2">
              <div className="mb-0.5 text-[10px] uppercase text-ink-faint">
                Acceptance criteria
              </div>
              <ul className="list-inside list-disc space-y-0.5 text-ink">
                {ac.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-[11px]">
            {metaKeys.map(([label, value]) => (
              <div key={label}>
                <span className="text-ink-faint">{label}: </span>
                <span className="text-ink">
                  {value === null || value === undefined || value === ""
                    ? "—"
                    : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {upstream.length > 0 && (
        <div>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Upstream agent inputs
          </h4>
          <ul className="space-y-1">
            {upstream.map((u, i) => (
              <li key={i} className="rounded border border-line bg-bg/50 px-2 py-1">
                <span className="mr-2 font-mono text-[10px] text-review">↑</span>
                <span className="text-ink">{u.agent_name}</span>
                <span className="ml-1 text-[10px] text-ink-faint">
                  (accepted output consumed)
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {artifacts.length > 0 && (
        <div>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            CI/CD artifacts analysed ({artifacts.length})
          </h4>
          <ul className="space-y-1">
            {artifacts.map((a, i) => (
              <li key={i} className="rounded border border-line bg-bg/50 px-2 py-1">
                <span className="mr-2 font-mono text-[10px] text-accent">{a.kind}</span>
                <span className="text-ink">{a.filename}</span>
                <p className="text-[10px] text-ink-dim">{a.summary}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rendered && (
        <div>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Rendered user prompt
          </h4>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded border border-line bg-bg p-2 font-mono text-[10px] leading-relaxed text-ink-dim">
            {rendered}
          </pre>
        </div>
      )}
    </div>
  );
}

function RunOutput({ output }: { output: Record<string, unknown> }) {
  const verdict = String(output.verdict ?? "");
  const verdictCls =
    verdict === "PASS" ? "text-ok" : verdict === "FAIL" ? "text-bad" : "text-warn";
  const findings = (output.findings ?? []) as Array<{
    title: string;
    detail: string;
    severity: string;
  }>;
  const extras = Object.entries(output).filter(([k]) => !ENVELOPE_KEYS.has(k));
  const confidence = output.confidence as
    | { level?: string; rationale?: string; caveats?: string[] }
    | undefined;
  const confCls =
    confidence?.level === "HIGH"
      ? "border-ok/50 bg-ok/10 text-ok"
      : confidence?.level === "LOW"
        ? "border-bad/50 bg-bad/10 text-bad"
        : "border-warn/50 bg-warn/10 text-warn";

  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`font-mono text-sm font-bold ${verdictCls}`}>{verdict}</span>
        {confidence?.level && (
          <Badge className={confCls}>◈ confidence {confidence.level}</Badge>
        )}
        {output.release_blocking === true && (
          <Badge className="border-bad/60 bg-bad/15 text-bad">
            ⛔ Release-blocking — no override
          </Badge>
        )}
      </div>
      <p className="leading-relaxed text-ink">{String(output.summary ?? "")}</p>

      {confidence && (
        <div className="rounded border border-line bg-bg/40 px-2 py-1.5">
          <span className="text-[11px] text-ink-dim">{confidence.rationale}</span>
          {(confidence.caveats ?? []).length > 0 && (
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-[10px] text-ink-faint">
              {(confidence.caveats ?? []).map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {findings.length > 0 && (
        <div>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Findings
          </h4>
          <ul className="space-y-1.5">
            {findings.map((f, i) => (
              <li key={i} className="rounded border border-line bg-bg/50 px-2 py-1.5">
                <span className={`mr-2 font-mono text-[10px] ${SEV_COLORS[f.severity] ?? ""}`}>
                  [{f.severity}]
                </span>
                <span className="font-medium text-ink">{f.title}</span>
                <p className="mt-0.5 text-ink-dim">{f.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {extras.map(([key, value]) => (
        <div key={key}>
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            {key.replaceAll("_", " ")}
          </h4>
          <ValueBlock value={value} />
        </div>
      ))}

      {typeof output.guidance_applied === "string" && output.guidance_applied && (
        <div className="rounded border border-review/40 bg-review/10 px-2 py-1.5 text-review">
          Re-run guidance applied: “{output.guidance_applied}”
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------ re-run diff

function RunDiff({ current, parent }: { current: Run; parent: Run }) {
  const a = parent.output_json ?? {};
  const b = current.output_json ?? {};
  const keys = Array.from(new Set([...Object.keys(a), ...Object.keys(b)])).filter(
    (k) => !["agent", "agent_name", "pact", "guidance_applied"].includes(k),
  );
  const changed = keys.filter(
    (k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]),
  );
  if (changed.length === 0)
    return (
      <p className="text-[11px] text-ink-faint">
        No differences from attempt {parent.attempt}.
      </p>
    );
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] text-ink-dim">
        Changed vs attempt {parent.attempt}: {changed.map((k) => k.replaceAll("_", " ")).join(", ")}
      </p>
      {changed.map((k) => (
        <details key={k} className="rounded border border-line bg-bg/50">
          <summary className="cursor-pointer px-2 py-1 text-[11px] font-medium text-ink-dim">
            {k.replaceAll("_", " ")}
          </summary>
          <div className="grid grid-cols-2 gap-2 p-2">
            <div>
              <div className="mb-1 text-[10px] uppercase text-bad">
                − attempt {parent.attempt}
              </div>
              <pre className="overflow-x-auto rounded bg-bad/5 p-1.5 font-mono text-[10px] text-ink-dim">
                {JSON.stringify(a[k], null, 2)}
              </pre>
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase text-ok">
                + attempt {current.attempt}
              </div>
              <pre className="overflow-x-auto rounded bg-ok/5 p-1.5 font-mono text-[10px] text-ink">
                {JSON.stringify(b[k], null, 2)}
              </pre>
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------- card

export function RunCard({
  run,
  parent,
  agent,
  actor,
  requireActor,
}: {
  run: Run;
  parent: Run | null;
  agent: AgentDef | undefined;
  actor: string;
  requireActor: () => boolean;
}) {
  const [modal, setModal] = useState<"reject" | "rerun" | null>(null);
  const [text, setText] = useState("");
  const [pushPreview, setPushPreview] = useState<PushItem | null>(null);
  const [view, setView] = useState<"output" | "input">("output");
  const [replayReport, setReplayReport] = useState<ReplayReport | null>(null);
  const [expanded, setExpanded] = useState(
    run.status === "COMPLETED" || run.status === "FAILED",
  );
  const toast = useToast();
  const queryClient = useQueryClient();
  const meta = RUN_STATUS_META[run.status];

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["story", run.story_id] });
    queryClient.invalidateQueries({ queryKey: ["stories"] });
    queryClient.invalidateQueries({ queryKey: ["timeline", run.story_id] });
  };

  const act = useMutation({
    mutationFn: async (action: () => Promise<unknown>) => action(),
    onSuccess: () => invalidate(),
    onError: (e: Error) => toast("error", e.message),
  });

  const draftMutation = useMutation({
    mutationFn: (kind: "agent_summary" | "bdd_scenarios") =>
      api.draftPush(kind, run.id, actor),
    onSuccess: (item) => setPushPreview(item),
    onError: (e: Error) => toast("error", e.message),
  });

  const replayMutation = useMutation({
    mutationFn: () => api.replayRun(run.id),
    onSuccess: (report) => setReplayReport(report),
    onError: (e: Error) => toast("error", e.message),
  });

  const approvePushMutation = useMutation({
    mutationFn: (id: string) => api.approvePush(id, actor),
    onSuccess: (item) => {
      setPushPreview(null);
      queryClient.invalidateQueries({ queryKey: ["push"] });
      if (item.status === "SENT") toast("ok", `Posted to ${item.payload.jira_key}`);
      else toast("error", `Push failed: ${item.last_error} — see the Jira Push Queue to retry`);
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const guard = (fn: () => void) => () => {
    if (!requireActor()) return;
    fn();
  };

  return (
    <div className="rounded-lg border border-line bg-panel">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left"
      >
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${meta.dot}`} />
        <span className="text-xs font-semibold text-ink">
          {agent?.name ?? run.agent_key}
        </span>
        {agent && <PactBadges pact={agent.pact} />}
        {run.attempt > 1 && (
          <Badge className="border-review/40 text-review">attempt {run.attempt}</Badge>
        )}
        <span className={`ml-auto text-[11px] font-medium ${meta.text}`}>
          {meta.label}
        </span>
        <span className="text-ink-faint">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="border-t border-line px-3 py-3">
          {/* provenance line */}
          <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-ink-faint">
            <span>prompt {run.prompt_version}</span>
            {run.model && <span>model {run.model}</span>}
            {run.token_usage?.input_tokens != null && (
              <span>
                tokens {run.token_usage.input_tokens}→{run.token_usage.output_tokens}
              </span>
            )}
            {run.input_hash && <span>in#{run.input_hash.slice(0, 10)}</span>}
            {run.output_hash && <span>out#{run.output_hash.slice(0, 10)}</span>}
            {run.approved_by && <span>approved by {run.approved_by} @ {fmtTime(run.started_at)}</span>}
            {run.decided_by && <span>decided by {run.decided_by} @ {fmtTime(run.decided_at)}</span>}
          </div>

          {run.guidance && (
            <div className="mb-3 rounded border border-review/40 bg-review/10 px-2 py-1.5 text-[11px] text-review">
              Guidance for this attempt: “{run.guidance}”
            </div>
          )}

          {run.status === "REJECTED" && run.decision_reason && (
            <div className="mb-3 rounded border border-bad/40 bg-bad/10 px-2 py-1.5 text-[11px] text-bad">
              Rejected: {run.decision_reason}
            </div>
          )}
          {run.status === "FAILED" && run.decision_reason && (
            <div className="mb-3 rounded border border-bad/40 bg-bad/10 px-2 py-1.5 text-[11px] text-bad">
              {run.decision_reason}
            </div>
          )}

          {/* Input / Output toggle */}
          {(run.input_json || run.output_json) && (
            <div className="mb-3 inline-flex rounded-md border border-line bg-bg/50 p-0.5">
              {(["output", "input"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  disabled={v === "input" ? !run.input_json : !run.output_json}
                  className={`rounded px-3 py-1 text-[11px] font-medium capitalize transition-colors disabled:opacity-30 ${
                    view === v ? "bg-accent/20 text-accent" : "text-ink-dim hover:text-ink"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          )}

          {view === "output" && run.output_json && (
            <RunOutput output={run.output_json} />
          )}
          {view === "input" && run.input_json && (
            <InputPanel input={run.input_json} />
          )}
          {view === "output" && !run.output_json && (
            <p className="text-[11px] text-ink-faint">
              No output yet — approve and run this agent to generate it.
            </p>
          )}

          {view === "output" && parent && parent.output_json && run.output_json && (
            <div className="mt-3 border-t border-line pt-3">
              <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Re-run comparison
              </h4>
              <RunDiff current={run} parent={parent} />
            </div>
          )}

          {/* actions */}
          <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
            {run.status === "AWAITING_APPROVAL" && (
              <Button
                variant="primary"
                busy={act.isPending}
                onClick={guard(() => act.mutate(() => api.approveRun(run.id, actor)))}
              >
                ▶ Approve &amp; Run
              </Button>
            )}
            {run.status === "COMPLETED" && (
              <>
                <Button
                  variant="ok"
                  busy={act.isPending}
                  onClick={guard(() => act.mutate(() => api.acceptRun(run.id, actor)))}
                >
                  ✓ Accept
                </Button>
                <Button variant="danger" onClick={guard(() => setModal("reject"))}>
                  ✗ Reject…
                </Button>
                <Button onClick={guard(() => setModal("rerun"))}>↻ Re-run with guidance…</Button>
              </>
            )}
            {(run.status === "REJECTED" || run.status === "FAILED") && (
              <Button onClick={guard(() => setModal("rerun"))}>↻ Re-run with guidance…</Button>
            )}
            {(run.status === "COMPLETED" ||
              run.status === "ACCEPTED" ||
              run.status === "REJECTED") &&
              run.output_hash && (
                <Button
                  busy={replayMutation.isPending}
                  onClick={() => replayMutation.mutate()}
                >
                  ⟲ Verify reproducibility
                </Button>
              )}
            {run.status === "ACCEPTED" && (
              <>
                <Button
                  busy={draftMutation.isPending}
                  onClick={guard(() => draftMutation.mutate("agent_summary"))}
                >
                  ↗ Post summary to Jira…
                </Button>
                {run.agent_key === "bdd_generator" && (
                  <Button
                    busy={draftMutation.isPending}
                    onClick={guard(() => draftMutation.mutate("bdd_scenarios"))}
                  >
                    ↗ Post BDD scenarios to Jira…
                  </Button>
                )}
              </>
            )}
          </div>

          {replayReport && (
            <div
              className={`mt-2 rounded border px-2.5 py-1.5 text-[11px] ${
                replayReport.status === "REPRODUCED"
                  ? "border-ok/50 bg-ok/10 text-ok"
                  : replayReport.status === "INPUT_DRIFT"
                    ? "border-warn/50 bg-warn/10 text-warn"
                    : "border-bad/50 bg-bad/10 text-bad"
              }`}
            >
              {replayReport.status === "REPRODUCED" && (
                <>
                  ✓ REPRODUCED — re-executed and matched the recorded hashes
                  byte-for-byte (out#
                  {replayReport.replay_output_hash.slice(0, 10)}). The audit
                  guarantee, demonstrated.
                </>
              )}
              {replayReport.status === "INPUT_DRIFT" && (
                <>
                  ⚠ INPUT DRIFT — inputs have changed since this run:{" "}
                  {replayReport.drift.join(", ")}. The recorded decision still
                  stands; a fresh run would see different inputs.
                </>
              )}
              {replayReport.status === "OUTPUT_DIVERGED" && (
                <>
                  ⛔ OUTPUT DIVERGED — same inputs, different output (
                  {replayReport.deterministic
                    ? "stored record does not match the deterministic replay — investigate tampering or a generator change"
                    : "model nondeterminism on the live path — comparison is advisory"}
                  ). Verdict stable: {String(replayReport.verdict_stable)}.
                </>
              )}
            </div>
          )}
        </div>
      )}

      {modal && (
        <Modal
          title={modal === "reject" ? "Reject agent output" : "Request re-run with guidance"}
          onClose={() => {
            setModal(null);
            setText("");
          }}
        >
          <Field
            label={
              modal === "reject"
                ? "Rejection reason (recorded immutably)"
                : "Guidance — injected into the agent's next prompt"
            }
          >
            <textarea
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              className={inputCls}
              placeholder={
                modal === "reject"
                  ? "Why is this output not acceptable?"
                  : "e.g. Focus on Consumer Duty outcomes; include negative paths for closed accounts"
              }
            />
          </Field>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setModal(null)}>
              Cancel
            </Button>
            <Button
              variant={modal === "reject" ? "danger" : "primary"}
              disabled={!text.trim()}
              busy={act.isPending}
              onClick={() => {
                const value = text.trim();
                act.mutate(() =>
                  modal === "reject"
                    ? api.rejectRun(run.id, actor, value)
                    : api.rerunRun(run.id, actor, value),
                );
                setModal(null);
                setText("");
              }}
            >
              {modal === "reject" ? "Reject" : "Create re-run"}
            </Button>
          </div>
        </Modal>
      )}

      {pushPreview && (
        <Modal title="Preview — post to Jira" onClose={() => setPushPreview(null)} wide>
          <p className="mb-2 text-[11px] text-ink-dim">
            This exact content will be posted as a comment on{" "}
            <span className="font-mono text-accent">{pushPreview.payload.jira_key}</span>.
            Nothing is sent until you approve.
          </p>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-line bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink">
            {pushPreview.payload.preview_text}
          </pre>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPushPreview(null)}>
              Cancel (stays in queue as draft)
            </Button>
            <Button
              variant="primary"
              busy={approvePushMutation.isPending}
              onClick={() => approvePushMutation.mutate(pushPreview.id)}
            >
              Approve &amp; send to Jira
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
