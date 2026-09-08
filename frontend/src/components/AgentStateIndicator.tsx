import type { AgentStateValue } from "@/lib/protocol";

const STATES: { key: AgentStateValue; label: string }[] = [
  { key: "listening", label: "Listening" },
  { key: "thinking", label: "Thinking" },
  { key: "calling_tool", label: "Calling tool" },
  { key: "speaking", label: "Speaking" },
];

export function AgentStateIndicator({ state, active }: { state: AgentStateValue; active: boolean }) {
  return (
    <div className="flex flex-col gap-1.5 p-4">
      <h2 className="mb-1 text-xs font-semibold tracking-wide text-neutral-400 uppercase">Agent State</h2>
      {STATES.map((s) => {
        const isCurrent = active && s.key === state;
        return (
          <div
            key={s.key}
            className={`flex items-center gap-2 rounded-md px-2 py-1 text-sm ${
              isCurrent
                ? "bg-blue-50 font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                : "text-neutral-400 dark:text-neutral-600"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${isCurrent ? "bg-blue-600" : "bg-neutral-300 dark:bg-neutral-700"}`}
            />
            {s.label}
          </div>
        );
      })}
    </div>
  );
}
