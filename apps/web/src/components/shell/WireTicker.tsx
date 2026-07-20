"use client";

/** The ambient wire ticker: source names + counts in Martian Mono, scrolling
 * slowly, pausing on tap. Honest data — it reads the live stage summary. */

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Wire } from "@/components/ui/primitives";

export function WireTicker() {
  const [entries, setEntries] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const s = await api.summary(120);
        if (!alive) return;
        const parts = Object.entries(s.stages).map(
          ([stage, m]) => `${stage} ${m.events}`,
        );
        setEntries(parts.length ? parts : ["wire idle"]);
      } catch {
        setEntries(["wire idle"]);
      }
    };
    void load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const line = entries.join("   ·   ");
  return (
    <button
      className="block w-full overflow-hidden border-b border-rule bg-graphite-2 py-1 text-left"
      onClick={() => setPaused((p) => !p)}
      aria-label={paused ? "resume ticker" : "pause ticker"}
    >
      <div
        ref={trackRef}
        className="whitespace-nowrap"
        style={{
          animation: paused ? "none" : "ticker 45s linear infinite",
        }}
      >
        <Wire tone="dim">{line}   ·   {line}   ·   {line}</Wire>
      </div>
      <style jsx>{`
        @keyframes ticker {
          from { transform: translateX(0); }
          to { transform: translateX(-33.33%); }
        }
      `}</style>
    </button>
  );
}
