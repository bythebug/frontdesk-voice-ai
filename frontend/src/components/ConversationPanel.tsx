import type { TranscriptEntry } from "@/lib/protocol";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

export function ConversationPanel({ transcripts }: { transcripts: TranscriptEntry[] }) {
  if (transcripts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-neutral-400 dark:text-neutral-600">
        Click &ldquo;Start Conversation&rdquo; and start talking.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 overflow-y-auto p-4">
      {transcripts.map((entry) => (
        <div key={entry.id} className={`flex flex-col ${entry.speaker === "user" ? "items-end" : "items-start"}`}>
          <div className="mb-1 flex items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
            <span className="font-medium capitalize">{entry.speaker === "user" ? "You" : "Agent"}</span>
            <span>{formatTime(entry.timestamp)}</span>
          </div>
          <div
            className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${
              entry.speaker === "user"
                ? "bg-blue-600 text-white"
                : "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
            }`}
          >
            {entry.text}
          </div>
        </div>
      ))}
    </div>
  );
}
