"use client";

import { Waveform } from "./Waveform";

interface VoiceControlsProps {
  isConnected: boolean;
  isRecording: boolean;
  micLevel: number;
  onStart: () => void;
  onStop: () => void;
}

export function VoiceControls({ isConnected, isRecording, micLevel, onStart, onStop }: VoiceControlsProps) {
  return (
    <div className="flex flex-col items-center gap-4 p-6">
      <button
        onClick={isConnected ? onStop : onStart}
        className={`flex h-20 w-20 items-center justify-center rounded-full text-white shadow-lg transition-transform active:scale-95 ${
          isConnected ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
        }`}
        aria-label={isConnected ? "Stop Conversation" : "Start Conversation"}
      >
        <MicIcon />
      </button>
      <span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
        {isConnected ? "Stop Conversation" : "Start Conversation"}
      </span>
      <div className="w-full max-w-xs">
        <Waveform level={micLevel} active={isRecording} />
      </div>
    </div>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-8 w-8">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}
