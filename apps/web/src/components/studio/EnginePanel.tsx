"use client";

/**
 * The Engine panel — pick a provider, paste a key, done.
 * Keys are stored in THIS browser only and travel per-request; the server
 * never persists them (the trace redaction guard enforces it). Demo mode
 * needs no key at all. FREE badges mark the no-money path.
 */

import { useEffect, useState } from "react";
import {
  loadEngine,
  PROVIDERS,
  saveEngine,
  type EngineConfig,
} from "@/lib/engine";
import { Wire } from "@/components/ui/primitives";

export function EnginePanel({ onNotice }: { onNotice: (s: string) => void }) {
  const [engine, setEngine] = useState<EngineConfig>({ provider: "", model: "", keys: {} });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setEngine(loadEngine());
    setLoaded(true);
  }, []);

  const update = (next: EngineConfig) => {
    setEngine(next);
    saveEngine(next);
  };

  if (!loaded) return null;

  const active =
    engine.provider ||
    (Object.entries(engine.keys).find(([, v]) => v.trim())?.[0] ?? "demo");

  return (
    <section className="mb-10">
      <Wire tone="machine">engine — who does the writing</Wire>
      <p className="mt-1 max-w-xl text-label text-silver-dim">
        Keys stay in <span className="text-silver">this browser</span> and are sent
        only with your own requests — the server never stores them. Start free:
        Demo needs nothing; Groq and Gemini are free tiers.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {PROVIDERS.map((p) => {
          const isActive = active === p.id;
          const hasKey = Boolean(engine.keys[p.id]?.trim());
          const needsKey = p.keyUrl !== "";
          return (
            <div
              key={p.id}
              className={`rounded-chrome p-4 transition-colors ${
                isActive
                  ? "bg-selenium-2 outline outline-1 outline-fixer-hot"
                  : "bg-selenium"
              }`}
            >
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    update({
                      ...engine,
                      provider: engine.provider === p.id ? "" : p.id,
                      model: "",
                    })
                  }
                  className="flex items-center gap-2 text-left"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isActive ? "bg-safelight" : hasKey ? "bg-fixer-hot" : "bg-graphite-2"
                    }`}
                  />
                  <span className="text-label font-semibold text-silver">{p.name}</span>
                </button>
                {p.free ? (
                  <span className="wire-label rounded-print bg-[#1d2b22] px-1.5 py-0.5 text-[#5FBF8F]">
                    free
                  </span>
                ) : null}
                {engine.provider === p.id ? (
                  <Wire tone="human" className="ml-auto">selected</Wire>
                ) : null}
              </div>
              <p className="mt-2 text-[12px] leading-snug text-silver-dim">{p.note}</p>
              {needsKey ? (
                <div className="mt-3 flex items-center gap-2">
                  <input
                    type="password"
                    value={engine.keys[p.id] ?? ""}
                    onChange={(e) =>
                      update({
                        ...engine,
                        keys: { ...engine.keys, [p.id]: e.target.value },
                      })
                    }
                    placeholder={p.keyHint || "api key"}
                    className="min-w-0 flex-1 rounded-print bg-graphite-2 px-3 py-1.5 font-mono text-[12px] text-silver outline-none placeholder:text-silver-dim/30"
                  />
                  <a
                    href={p.keyUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="wire-label whitespace-nowrap text-safelight"
                  >
                    get key ↗
                  </a>
                </div>
              ) : null}
              {isActive && p.id !== "demo" ? (
                <input
                  value={engine.model}
                  onChange={(e) => update({ ...engine, model: e.target.value })}
                  placeholder={`model (default: ${p.defaultModel})`}
                  className="mt-2 w-full rounded-print bg-graphite-2 px-3 py-1.5 font-mono text-[11px] text-silver-dim outline-none placeholder:text-silver-dim/30"
                />
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex items-center gap-4">
        <Wire tone={active === "demo" ? "machine" : "hot"}>
          active engine: {active}
        </Wire>
        <button
          onClick={() => {
            update({ provider: "", model: "", keys: {} });
            onNotice("Engine cleared — back to auto (demo until a key is added).");
          }}
        >
          <Wire tone="reject">clear all keys</Wire>
        </button>
      </div>
    </section>
  );
}
