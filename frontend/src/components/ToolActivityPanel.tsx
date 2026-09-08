import type { ToolActivityEntry } from "@/lib/protocol";

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
}

export function ToolActivityPanel({ activity }: { activity: ToolActivityEntry[] }) {
  return (
    <div className="flex flex-col gap-2 p-4">
      <h2 className="text-xs font-semibold tracking-wide text-neutral-400 uppercase">Tool Activity</h2>
      {activity.length === 0 && (
        <p className="text-sm text-neutral-400 dark:text-neutral-600">No tools called yet.</p>
      )}
      {activity
        .slice()
        .reverse()
        .map((entry) => (
          <div
            key={entry.id}
            className="rounded-lg border border-neutral-200 p-3 text-sm dark:border-neutral-800"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium">{entry.tool}</span>
              <StatusBadge status={entry.status} />
            </div>
            {formatArgs(entry.arguments) && (
              <p className="mt-1 truncate text-xs text-neutral-500 dark:text-neutral-400">
                {formatArgs(entry.arguments)}
              </p>
            )}
            {entry.status === "error" && entry.error && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{entry.error}</p>
            )}
          </div>
        ))}
    </div>
  );
}

function StatusBadge({ status }: { status: ToolActivityEntry["status"] }) {
  if (status === "pending") {
    return <span className="text-xs text-amber-600 dark:text-amber-400">Running…</span>;
  }
  if (status === "success") {
    return <span className="text-xs text-emerald-600 dark:text-emerald-400">✓ Completed</span>;
  }
  return <span className="text-xs text-red-600 dark:text-red-400">✗ Failed</span>;
}
