"use client";

import { useState, type FormEvent } from "react";

interface TextFallbackProps {
  disabled: boolean;
  onSend: (text: string) => void;
}

// Voice is the primary input, but the backend's user_text message has been
// fully supported since Phase 5 — this just gives it a UI control, useful
// for testing, accessibility, and quiet environments.
export function TextFallback({ disabled, onSend }: TextFallbackProps) {
  const [value, setValue] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex gap-2 border-t border-neutral-200 p-3 dark:border-neutral-800"
    >
      <input
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled}
        placeholder={disabled ? "Start a conversation to send a message" : "Or type a message..."}
        className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
      >
        Send
      </button>
    </form>
  );
}
