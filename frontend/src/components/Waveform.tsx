"use client";

import { useEffect, useRef } from "react";

const HISTORY_LENGTH = 40;

export function Waveform({ level, active }: { level: number; active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const historyRef = useRef<number[]>(new Array(HISTORY_LENGTH).fill(0));

  useEffect(() => {
    const history = historyRef.current;
    history.push(active ? level : 0);
    history.shift();

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    const barWidth = width / HISTORY_LENGTH;
    ctx.fillStyle = active ? "#2563eb" : "#d4d4d4";

    history.forEach((value, i) => {
      const barHeight = Math.max(2, Math.min(1, value * 8) * height);
      ctx.fillRect(i * barWidth, (height - barHeight) / 2, barWidth * 0.6, barHeight);
    });
  }, [level, active]);

  return <canvas ref={canvasRef} width={280} height={48} className="w-full" />;
}
