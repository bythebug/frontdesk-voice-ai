// Mirrors backend/app/api/websocket.py's message protocol exactly.

export type AgentStateValue = "listening" | "thinking" | "calling_tool" | "speaking";
export type Speaker = "user" | "agent";

export type ServerMessage =
  | { type: "conversation_started"; conversation_id: string }
  | { type: "transcript"; speaker: Speaker; text: string; timestamp: string }
  | { type: "agent_state"; state: AgentStateValue }
  | { type: "tool_call"; tool: string; arguments: Record<string, unknown> }
  | {
      type: "tool_result";
      tool: string;
      success: boolean;
      data: Record<string, unknown> | null;
      error: string | null;
    }
  | { type: "audio"; data: string }
  | { type: "conversation_ended"; conversation_id: string }
  | { type: "error"; message: string };

export type ClientMessage =
  | { type: "user_text"; text: string }
  | { type: "audio_chunk"; data: string }
  | { type: "audio_end" }
  | { type: "end_conversation" };

export interface TranscriptEntry {
  id: string;
  speaker: Speaker;
  text: string;
  timestamp: string;
}

export interface ToolActivityEntry {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: "pending" | "success" | "error";
  data: Record<string, unknown> | null;
  error: string | null;
}

export type ConnectionStatus = "offline" | "connecting" | "connected" | "error";
