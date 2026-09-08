import type { ServerMessage } from "@/lib/protocol";

export type CallSummaryData = Extract<ServerMessage, { type: "call_summary" }>;

export function CallSummaryPanel({ summary }: { summary: CallSummaryData }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="text-sm font-semibold">Call Summary</h2>
      <SummaryRow label="Intent" value={summary.intent ?? "—"} />
      <SummaryRow label="Customer" value={summary.customer_name ?? "—"} />
      <SummaryRow
        label="Appointment"
        value={summary.appointment ? `${summary.appointment.date}, ${summary.appointment.time}` : "—"}
      />
      <SummaryRow label="Issue" value={summary.issue ?? "—"} />
      <SummaryRow label="Outcome" value={summary.outcome} />
      <div>
        <p className="text-xs font-medium text-neutral-400">Tools Used</p>
        <p className="text-sm">{summary.tools_used.length ? summary.tools_used.join(", ") : "None"}</p>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-neutral-400">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  );
}
