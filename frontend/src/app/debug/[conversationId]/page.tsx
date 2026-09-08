const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TimelineEvent {
  event_type: string;
  timestamp: string;
  speaker: string | null;
  text: string | null;
  tool_name: string | null;
  status: string | null;
  latency_ms: number | null;
}

interface TimelineResponse {
  conversation_id: string;
  status: string;
  events: TimelineEvent[];
}

async function getTimeline(conversationId: string): Promise<TimelineResponse | null> {
  try {
    const res = await fetch(`${API_URL}/api/conversations/${conversationId}/timeline`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as TimelineResponse;
  } catch {
    return null;
  }
}

function formatLine(event: TimelineEvent): string {
  const time = new Date(event.timestamp).toLocaleTimeString([], { hour12: false });
  const label = event.event_type.padEnd(24);
  const detail =
    event.event_type === "TOOL_CALL"
      ? `${event.tool_name}${event.latency_ms !== null ? `  ${event.latency_ms}ms` : ""}  [${event.status}]`
      : (event.text ?? "");
  return `${time}  ${label}${detail}`;
}

export default async function DebugTimelinePage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  const timeline = await getTimeline(conversationId);

  return (
    <div className="min-h-screen p-6">
      <h1 className="mb-1 text-lg font-semibold">Conversation Timeline</h1>
      <p className="mb-4 font-mono text-sm text-neutral-500">{conversationId}</p>
      {!timeline ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          Conversation not found (or the backend is unreachable).
        </p>
      ) : (
        <>
          <p className="mb-4 text-sm text-neutral-500">Status: {timeline.status}</p>
          <pre className="overflow-x-auto rounded-lg bg-neutral-900 p-4 font-mono text-sm text-neutral-100">
            {timeline.events.map(formatLine).join("\n") || "(no events yet)"}
          </pre>
        </>
      )}
    </div>
  );
}
