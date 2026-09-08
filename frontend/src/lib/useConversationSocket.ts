"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CallSummaryData } from "@/components/CallSummaryPanel";
import {
  arrayBufferToBase64,
  base64ToArrayBuffer,
  downsampleTo16k,
  floatTo16BitPCM,
  pcm16ToFloat32,
  rms,
  TARGET_SAMPLE_RATE,
} from "./audio";
import type {
  AgentStateValue,
  ClientMessage,
  ConnectionStatus,
  ServerMessage,
  ToolActivityEntry,
  TranscriptEntry,
} from "./protocol";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

// Silence detection: after this many ms of low amplitude following speech,
// automatically end the user's turn and send audio_end. A simple amplitude
// threshold, not a real VAD model — documented limitation; upgrade path is
// a proper VAD (e.g. WebRTC VAD) if false triggers become a problem.
const SILENCE_RMS_THRESHOLD = 0.02;
const SILENCE_DURATION_MS = 1200;

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `${Date.now()}-${idCounter}`;
}

export function useConversationSocket() {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("offline");
  const [agentState, setAgentState] = useState<AgentStateValue>("listening");
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);
  const [toolActivity, setToolActivity] = useState<ToolActivityEntry[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [callSummary, setCallSummary] = useState<CallSummaryData | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const captureContextRef = useRef<AudioContext | null>(null);
  const silenceStartRef = useRef<number | null>(null);
  const hasSpokenRef = useRef(false);
  const playbackQueueRef = useRef<Promise<void>>(Promise.resolve());
  const playbackContextRef = useRef<AudioContext | null>(null);
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const agentStateRef = useRef<AgentStateValue>("listening");

  const send = useCallback((message: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Real barge-in on the client: stop whatever's currently playing the
  // instant the user starts talking again, rather than waiting for the
  // server's "interrupted" frame — that's the practical way to interrupt
  // audio that has *already* been sent (the server can cancel further
  // work, but can't un-send bytes already on the wire).
  const stopPlayback = useCallback(() => {
    currentSourceRef.current?.stop();
    currentSourceRef.current = null;
    playbackQueueRef.current = Promise.resolve();
  }, []);

  const playAudio = useCallback(async (base64: string) => {
    const buffer = base64ToArrayBuffer(base64);
    const samples = pcm16ToFloat32(buffer);
    if (samples.length === 0) return;

    if (!playbackContextRef.current) {
      playbackContextRef.current = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
    }
    const ctx = playbackContextRef.current;
    const audioBuffer = ctx.createBuffer(1, samples.length, TARGET_SAMPLE_RATE);
    audioBuffer.copyToChannel(samples, 0);

    playbackQueueRef.current = playbackQueueRef.current.then(
      () =>
        new Promise<void>((resolve) => {
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(ctx.destination);
          source.onended = () => {
            if (currentSourceRef.current === source) currentSourceRef.current = null;
            resolve();
          };
          currentSourceRef.current = source;
          source.start();
        }),
    );
    await playbackQueueRef.current;
  }, []);

  const handleServerMessage = useCallback(
    (message: ServerMessage) => {
      switch (message.type) {
        case "conversation_started":
          setConversationId(message.conversation_id);
          break;
        case "transcript":
          setTranscripts((prev) => [
            ...prev,
            {
              id: nextId(),
              speaker: message.speaker,
              text: message.text,
              timestamp: message.timestamp,
            },
          ]);
          break;
        case "agent_state":
          agentStateRef.current = message.state;
          setAgentState(message.state);
          break;
        case "tool_call":
          setToolActivity((prev) => [
            ...prev,
            {
              id: nextId(),
              tool: message.tool,
              arguments: message.arguments,
              status: "pending",
              data: null,
              error: null,
            },
          ]);
          break;
        case "tool_result":
          setToolActivity((prev) => {
            const next = [...prev];
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].tool === message.tool && next[i].status === "pending") {
                next[i] = {
                  ...next[i],
                  status: message.success ? "success" : "error",
                  data: message.data,
                  error: message.error,
                };
                break;
              }
            }
            return next;
          });
          break;
        case "audio":
          void playAudio(message.data);
          break;
        case "call_summary":
          setCallSummary(message);
          break;
        case "conversation_ended":
          setConnectionStatus("offline");
          break;
        case "error":
          setErrorMessage(message.message);
          break;
      }
    },
    [playAudio],
  );

  const stopMic = useCallback(() => {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    void captureContextRef.current?.close();
    captureContextRef.current = null;
    setIsRecording(false);
    setMicLevel(0);
  }, []);

  const startMic = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = stream;

    const audioContext = new AudioContext();
    captureContextRef.current = audioContext;
    const source = audioContext.createMediaStreamSource(stream);
    sourceRef.current = source;

    // ScriptProcessorNode is deprecated in favor of AudioWorklet; kept here
    // for simplicity (no separate worklet module to load/serve). Upgrade to
    // AudioWorkletNode if broader browser/future-proofing matters.
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;

    hasSpokenRef.current = false;
    silenceStartRef.current = null;

    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const level = rms(input);
      setMicLevel(level);

      const downsampled = downsampleTo16k(input, audioContext.sampleRate);
      const pcm = floatTo16BitPCM(downsampled);
      send({ type: "audio_chunk", data: arrayBufferToBase64(pcm) });

      const now = performance.now();
      if (level > SILENCE_RMS_THRESHOLD) {
        if (agentStateRef.current === "speaking" && currentSourceRef.current) {
          stopPlayback();
        }
        hasSpokenRef.current = true;
        silenceStartRef.current = null;
      } else if (hasSpokenRef.current) {
        if (silenceStartRef.current === null) {
          silenceStartRef.current = now;
        } else if (now - silenceStartRef.current > SILENCE_DURATION_MS) {
          send({ type: "audio_end" });
          hasSpokenRef.current = false;
          silenceStartRef.current = null;
        }
      }
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
    setIsRecording(true);
  }, [send, stopPlayback]);

  const start = useCallback(async () => {
    setErrorMessage(null);
    setCallSummary(null);
    setTranscripts([]);
    setToolActivity([]);
    setConnectionStatus("connecting");
    const ws = new WebSocket(`${WS_URL}/ws/conversation`);
    wsRef.current = ws;

    ws.onopen = () => setConnectionStatus("connected");
    ws.onclose = () => {
      setConnectionStatus("offline");
      stopMic();
    };
    ws.onerror = () => setConnectionStatus("error");
    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const message = JSON.parse(event.data) as ServerMessage;
        handleServerMessage(message);
      } catch {
        setErrorMessage("Received a malformed message from the server.");
      }
    };

    try {
      await startMic();
    } catch {
      setErrorMessage("Microphone access was denied or unavailable.");
    }
  }, [handleServerMessage, startMic, stopMic]);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      send({ type: "end_conversation" });
    }
    stopMic();
    wsRef.current?.close();
    wsRef.current = null;
  }, [send, stopMic]);

  const sendText = useCallback(
    (text: string) => {
      send({ type: "user_text", text });
    },
    [send],
  );

  useEffect(() => {
    return () => {
      stopMic();
      wsRef.current?.close();
    };
    // Cleanup should only run on unmount, not on every dependency change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    connectionStatus,
    agentState,
    transcripts,
    toolActivity,
    conversationId,
    isRecording,
    micLevel,
    errorMessage,
    callSummary,
    start,
    stop,
    sendText,
  };
}
