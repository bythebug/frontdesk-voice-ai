// Shape matches the call_summaries table (backend/app/db/models.py). The
// backend doesn't send this over the wire yet — Phase 11 adds a
// "call_summary" server message and wires it into page.tsx; this component
// is built now (per the Phase 10 spec) but stays unrendered until then.
export interface CallSummaryData {
  intent: string | null;
  customerName: string | null;
  appointment: { date: string; time: string } | null;
  issue: string | null;
  outcome: string;
  toolsUsed: string[];
}

export function CallSummaryPanel({ summary }: { summary: CallSummaryData }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="text-sm font-semibold">Call Summary</h2>
      <SummaryRow label="Intent" value={summary.intent ?? "—"} />
      <SummaryRow label="Customer" value={summary.customerName ?? "—"} />
      <SummaryRow
        label="Appointment"
        value={summary.appointment ? `${summary.appointment.date}, ${summary.appointment.time}` : "—"}
      />
      <SummaryRow label="Issue" value={summary.issue ?? "—"} />
      <SummaryRow label="Outcome" value={summary.outcome} />
      <div>
        <p className="text-xs font-medium text-neutral-400">Tools Used</p>
        <p className="text-sm">{summary.toolsUsed.length ? summary.toolsUsed.join(", ") : "None"}</p>
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
