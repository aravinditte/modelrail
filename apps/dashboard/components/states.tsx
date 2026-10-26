import { ApiError } from "@/lib/api";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-zinc-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700 dark:border-zinc-700 dark:border-t-zinc-200" />
      {label}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 px-4 py-10 text-center dark:border-zinc-700">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-zinc-500">{hint}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const denied = error instanceof ApiError && error.isPermissionDenied;
  const unreachable = error instanceof ApiError && error.status === 0;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-6 dark:border-red-900 dark:bg-red-950/40" role="alert">
      <p className="text-sm font-semibold text-red-800 dark:text-red-200">
        {denied ? "Permission denied" : unreachable ? "Gateway unreachable" : "Failed to load"}
      </p>
      <p className="mt-1 text-sm text-red-700 dark:text-red-300">{message}</p>
      {denied && (
        <p className="mt-1 text-sm text-red-700 dark:text-red-300">
          Enter a valid admin token in the header above, then retry.
        </p>
      )}
      {onRetry && (
        <button onClick={onRetry} className="mt-3 rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-100 dark:border-red-800 dark:text-red-200 dark:hover:bg-red-900/50">
          Retry
        </button>
      )}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "green" | "red" | "amber" }) {
  const tones = {
    neutral: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  } as const;
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function statusTone(status?: string): "green" | "red" | "amber" | "neutral" {
  const s = (status || "").toLowerCase();
  if (["succeeded", "success", "completed", "ok", "active", "passed", "pass"].includes(s)) return "green";
  if (["failed", "error", "failure", "regression", "regressed"].includes(s)) return "red";
  if (["running", "pending", "queued", "in_progress"].includes(s)) return "amber";
  return "neutral";
}

export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      {sub && <p className="mt-1 text-sm text-zinc-500">{sub}</p>}
    </div>
  );
}

export function formatCost(v: unknown): string {
  const n = typeof v === "string" ? Number(v) : (v as number);
  return typeof n === "number" && Number.isFinite(n) ? `$${n.toFixed(4)}` : "—";
}
export function formatDate(v: unknown): string {
  if (!v) return "—";
  const d = new Date(String(v));
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
}
