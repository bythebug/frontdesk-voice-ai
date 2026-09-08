import type { AgentStateValue, ConnectionStatus } from "@/lib/protocol";

export type HeaderStatus =
  | "offline"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "error";

export function deriveHeaderStatus(
  connectionStatus: ConnectionStatus,
  agentState: AgentStateValue,
): HeaderStatus {
  if (connectionStatus === "offline") return "offline";
  if (connectionStatus === "connecting") return "connecting";
  if (connectionStatus === "error") return "error";
  if (agentState === "calling_tool") return "thinking";
  return agentState;
}

const STATUS_STYLES: Record<HeaderStatus, string> = {
  offline: "bg-neutral-200 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
  connecting: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  listening: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  thinking: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  speaking: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  interrupted: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  error: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

const STATUS_LABELS: Record<HeaderStatus, string> = {
  offline: "Offline",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  interrupted: "Interrupted",
  error: "Error",
};

export function Header({ status }: { status: HeaderStatus }) {
  return (
    <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">FrontDeskAI</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Real-Time AI Support Agent</p>
      </div>
      <span
        className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_STYLES[status]}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {STATUS_LABELS[status]}
      </span>
    </header>
  );
}
