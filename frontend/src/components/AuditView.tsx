import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import { fmtTime } from "../ui";

export function AuditView() {
  const [entityType, setEntityType] = useState("");
  const [eventType, setEventType] = useState("");
  const [actorFilter, setActorFilter] = useState("");

  const params = useMemo(() => {
    const p: Record<string, string> = { limit: "200" };
    if (entityType) p.entity_type = entityType;
    if (eventType) p.event_type = eventType;
    if (actorFilter) p.actor = actorFilter;
    return p;
  }, [entityType, eventType, actorFilter]);

  const auditQuery = useQuery({
    queryKey: ["audit", params],
    queryFn: () => api.audit(params),
  });
  const verifyQuery = useQuery({
    queryKey: ["audit-verify"],
    queryFn: api.auditVerify,
    refetchInterval: 60000,
  });

  const exportUrl = (format: string) =>
    `/api/v1/audit/export?${new URLSearchParams({ ...params, format })}`;

  const events = auditQuery.data ?? [];
  const eventTypes = useMemo(
    () => Array.from(new Set(events.map((e) => e.event_type))).sort(),
    [events],
  );

  return (
    <div className="stage">
      <div className="board-head">
        <div className="board-title">Audit Trail</div>
        <div className="board-sub">Append-only, hash-chained event log · 7-year retention</div>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <div className="meta-label" style={{ textAlign: "left" }}>Entity type</div>
          <select value={entityType} onChange={(e) => setEntityType(e.target.value)} className="role-select">
            <option value="">All</option>
            {["story", "agent_run", "gate", "push", "sync", "settings"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="meta-label" style={{ textAlign: "left" }}>Event type</div>
          <select value={eventType} onChange={(e) => setEventType(e.target.value)} className="role-select">
            <option value="">All</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <div className="meta-label" style={{ textAlign: "left" }}>Actor</div>
          <input
            value={actorFilter}
            onChange={(e) => setActorFilter(e.target.value)}
            placeholder="exact name"
            className="role-select"
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {verifyQuery.data && (
            <span className={`pill ${verifyQuery.data.valid ? "pill-good" : "pill-crit"}`}>
              {verifyQuery.data.valid
                ? `⛓ chain verified · ${verifyQuery.data.events} events`
                : "⛓ CHAIN BROKEN — investigate"}
            </span>
          )}
          <a href={exportUrl("csv")} download><button type="button" className="ghost-btn">↓ CSV</button></a>
          <a href={exportUrl("json")} download><button type="button" className="ghost-btn">↓ JSON</button></a>
        </div>
      </div>

      <p className="mb-3 font-mono text-[10px] text-ink-faint">
        No edit or delete exists — enforced by API surface, ORM and database triggers.
      </p>

      <div className="panel-block" style={{ padding: 0 }}>
        <div className="dtable" style={{ padding: 16, overflowX: "auto" }}>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>#</th><th>Time</th><th>Event</th><th>Entity</th><th>Actor</th><th>Payload</th><th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td className="mono">{event.id}</td>
                  <td className="mono" style={{ whiteSpace: "nowrap" }}>{fmtTime(event.created_at)}</td>
                  <td style={{ fontWeight: 500 }}>{event.event_type.replaceAll("_", " ")}</td>
                  <td className="text-ink-dim">{event.entity_type}</td>
                  <td className="text-ink-dim">{event.actor}</td>
                  <td style={{ maxWidth: 320 }}>
                    <details>
                      <summary className="cursor-pointer truncate font-mono text-[10.5px] text-ink-faint">
                        {Object.keys(event.payload).slice(0, 4).join(", ") || "—"}
                      </summary>
                      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-bg p-2 font-mono text-[10px] text-ink-dim">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </details>
                  </td>
                  <td className="mono">{event.event_hash.slice(0, 10)}</td>
                </tr>
              ))}
              {events.length === 0 && !auditQuery.isLoading && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "32px 0" }} className="text-ink-faint">
                    No events match the filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
