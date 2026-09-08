"use client";

import { useState } from "react";
import { AgentStateIndicator } from "@/components/AgentStateIndicator";
import type { CallSummaryData } from "@/components/CallSummaryPanel";
import { CallSummaryPanel } from "@/components/CallSummaryPanel";
import { ConversationPanel } from "@/components/ConversationPanel";
import { deriveHeaderStatus, Header } from "@/components/Header";
import { ToolActivityPanel } from "@/components/ToolActivityPanel";
import { VoiceControls } from "@/components/VoiceControls";
import { useConversationSocket } from "@/lib/useConversationSocket";

export default function Home() {
  const {
    connectionStatus,
    agentState,
    transcripts,
    toolActivity,
    isRecording,
    micLevel,
    errorMessage,
    start,
    stop,
  } = useConversationSocket();

  // Populated once the backend sends a call_summary message (Phase 11).
  const [callSummary] = useState<CallSummaryData | null>(null);

  const isConnected = connectionStatus === "connected" || connectionStatus === "connecting";
  const headerStatus = deriveHeaderStatus(connectionStatus, agentState);

  return (
    <div className="flex min-h-screen flex-col">
      <Header status={headerStatus} />

      {errorMessage && (
        <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {errorMessage}
        </div>
      )}

      <main className="grid flex-1 grid-cols-1 lg:grid-cols-[1fr_320px]">
        <section className="flex min-h-0 flex-col border-r border-neutral-200 dark:border-neutral-800">
          <div className="min-h-0 flex-1">
            <ConversationPanel transcripts={transcripts} />
          </div>
          <div className="border-t border-neutral-200 dark:border-neutral-800">
            <VoiceControls
              isConnected={isConnected}
              isRecording={isRecording}
              micLevel={micLevel}
              onStart={start}
              onStop={stop}
            />
          </div>
        </section>

        <aside className="flex flex-col divide-y divide-neutral-200 overflow-y-auto dark:divide-neutral-800">
          <AgentStateIndicator state={agentState} active={connectionStatus === "connected"} />
          <ToolActivityPanel activity={toolActivity} />
          {callSummary && (
            <div className="p-4">
              <CallSummaryPanel summary={callSummary} />
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
