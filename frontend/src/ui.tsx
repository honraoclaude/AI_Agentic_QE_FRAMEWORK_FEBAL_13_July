import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { GateStatus, RunStatus } from "./types";

// ------------------------------------------------------------------ tokens

export const RUN_STATUS_META: Record<
  RunStatus,
  { label: string; dot: string; text: string }
> = {
  PROPOSED: { label: "Pending", dot: "bg-ink-faint", text: "text-ink-faint" },
  AWAITING_APPROVAL: { label: "Awaiting approval", dot: "bg-warn", text: "text-warn" },
  RUNNING: { label: "Running", dot: "bg-accent animate-pulse-dot", text: "text-accent" },
  COMPLETED: { label: "Review output", dot: "bg-review", text: "text-review" },
  ACCEPTED: { label: "Accepted", dot: "bg-ok", text: "text-ok" },
  REJECTED: { label: "Rejected", dot: "bg-bad", text: "text-bad" },
  RERUN_REQUESTED: { label: "Superseded", dot: "bg-ink-faint", text: "text-ink-faint" },
  SKIPPED: { label: "Skipped (disabled)", dot: "bg-ink-faint", text: "text-ink-faint" },
  FAILED: { label: "Failed", dot: "bg-bad animate-pulse-dot", text: "text-bad" },
};

export const GATE_STATUS_META: Record<
  GateStatus,
  { label: string; cls: string }
> = {
  LOCKED: { label: "Locked", cls: "border-line text-ink-faint" },
  READY_FOR_SIGNOFF: {
    label: "Ready for sign-off",
    cls: "border-warn/60 text-warn bg-warn/10",
  },
  SIGNED_OFF: { label: "Signed off", cls: "border-ok/60 text-ok bg-ok/10" },
  REJECTED: { label: "Rejected", cls: "border-bad/60 text-bad bg-bad/10" },
};

export const PACT_COLORS: Record<string, string> = {
  Proactive: "bg-sky-400/15 text-sky-300 border-sky-400/30",
  Autonomous: "bg-violet-400/15 text-violet-300 border-violet-400/30",
  Collaborative: "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
  Targeted: "bg-amber-400/15 text-amber-300 border-amber-400/30",
};

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// -------------------------------------------------------------- primitives

export function Badge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${className}`}
    >
      {children}
    </span>
  );
}

export function PactBadges({ pact }: { pact: string[] }) {
  return (
    <span className="inline-flex gap-1">
      {pact.map((p) => (
        <Badge key={p} className={PACT_COLORS[p] ?? "border-line text-ink-dim"}>
          {p}
        </Badge>
      ))}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  busy,
  className = "",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "ok" | "danger" | "ghost";
  disabled?: boolean;
  busy?: boolean;
  className?: string;
  title?: string;
}) {
  const variants: Record<string, string> = {
    default: "border-line bg-panel-2 hover:border-ink-faint text-ink",
    primary: "border-accent/50 bg-accent/15 hover:bg-accent/25 text-accent",
    ok: "border-ok/50 bg-ok/15 hover:bg-ok/25 text-ok",
    danger: "border-bad/50 bg-bad/15 hover:bg-bad/25 text-bad",
    ghost: "border-transparent hover:bg-panel-2 text-ink-dim hover:text-ink",
  };
  return (
    <button
      title={title}
      disabled={disabled || busy}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${className}`}
    >
      {busy && (
        <span className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`max-h-[85vh] w-full ${wide ? "max-w-3xl" : "max-w-xl"} overflow-y-auto rounded-xl border border-line bg-panel p-5 shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-ink-dim">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="text-ink-faint transition-colors hover:text-ink"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full rounded-md border border-line bg-panel-2 px-2.5 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none";

// ------------------------------------------------------------------- toast

interface Toast {
  id: number;
  kind: "ok" | "error" | "info";
  text: string;
}

const ToastContext = createContext<(kind: Toast["kind"], text: string) => void>(
  () => {},
);

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    window.setTimeout(
      () => setToasts((t) => t.filter((x) => x.id !== id)),
      kind === "error" ? 8000 : 5000,
    );
  }, []);
  const colors = {
    ok: "border-ok/50 text-ok",
    error: "border-bad/50 text-bad",
    info: "border-accent/50 text-accent",
  };
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-96 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-lg border bg-panel px-4 py-3 text-sm shadow-xl ${colors[t.kind]}`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
