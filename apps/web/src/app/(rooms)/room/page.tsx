"use client";

/**
 * THE WIRE ROOM — every backend process, visible and live.
 *
 * Data: SSE from /events/stream (reconnect + replay from last id), meters
 * from /events/summary + /system/meters every 5s. The raw log is never
 * polled. Particles are real items in transit; when nothing is happening,
 * nothing moves — no idle animation, ever.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, eventStreamUrl, MetersResponse } from "@/lib/api";
import { Print, Wire } from "@/components/ui/primitives";
import { z } from "zod";

const STAGES = [
  "fetch",
  "embed",
  "cluster",
  "brief",
  "rank",
  "you",
  "generate",
  "publish",
] as const;

type StageName = (typeof STAGES)[number];

interface PipelineEvent {
  id: string;
  trace_id: string;
  stage: string;
  status: string;
  entity_type: string;
  entity_id: string;
  duration_ms: number | null;
  payload: Record<string, unknown>;
  error: Record<string, unknown> | null;
  created_at: string;
}

type Meters = z.infer<typeof MetersResponse>;

export default function WireRoomPage() {
  const [counters, setCounters] = useState<Record<string, number>>({});
  const [pulses, setPulses] = useState<Record<string, number>>({});
  const [failing, setFailing] = useState<Record<string, number>>({});
  const [meters, setMeters] = useState<Meters | null>(null);
  const [summary, setSummary] = useState<Record<string, { events: number; p95_ms: number | null; error_rate: number; cost_cents: number }>>({});
  const [selected, setSelected] = useState<StageName | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const [followTrace, setFollowTrace] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<PipelineEvent[]>([]);
  const lastId = useRef<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const backoff = useRef(1000);

  const connect = useCallback(() => {
    esRef.current?.close();
    const url = new URL(eventStreamUrl(), window.location.origin);
    if (lastId.current) url.searchParams.set("last_event_id", lastId.current);
    const es = new EventSource(url.toString());
    esRef.current = es;
    es.addEventListener("pipeline", (msg) => {
      backoff.current = 1000;
      const event = JSON.parse((msg as MessageEvent).data) as PipelineEvent;
      lastId.current = event.id;
      if (paused) return;
      const stage = event.stage as StageName;
      if (event.status === "succeeded" || event.status === "failed") {
        setCounters((c) => ({ ...c, [stage]: (c[stage] ?? 0) + 1 }));
        setPulses((p) => ({ ...p, [stage]: Date.now() }));
        if (event.status === "failed") {
          setFailing((f) => ({ ...f, [stage]: Date.now() }));
        }
      }
      setEvents((prev) => [event, ...prev].slice(0, 400));
      if (followTrace && event.trace_id === followTrace) {
        setTraceEvents((prev) => [...prev, event]);
      }
    });
    es.onerror = () => {
      es.close();
      setTimeout(connect, backoff.current);
      backoff.current = Math.min(backoff.current * 2, 30000);
    };
  }, [paused, followTrace]);

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
  }, [connect]);

  useEffect(() => {
    const load = async () => {
      try {
        const [m, s] = await Promise.all([api.meters(), api.summary(60)]);
        setMeters(m);
        setSummary(s.stages);
      } catch {
        /* meters wait for auth */
      }
    };
    void load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const follow = async (traceId: string) => {
    setFollowTrace(traceId);
    const res = (await api.trace(traceId)) as { events?: PipelineEvent[] };
    setTraceEvents(res.events ?? []);
  };

  const stageEvents = selected
    ? events.filter((e) => e.stage === selected).slice(0, 50)
    : [];

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* METERS — thin bars in mono. No gauges, no dials. */}
      <div className="grid grid-cols-2 gap-6 border-b border-rule pb-6 lg:grid-cols-4">
        <Meter
          label={`YouTube units · ${meters?.youtube_units.used ?? 0} / ${meters?.youtube_units.cap ?? 10000}`}
          value={(meters?.youtube_units.used ?? 0) / (meters?.youtube_units.cap ?? 10000)}
          danger={(meters?.youtube_units.used ?? 0) / (meters?.youtube_units.cap ?? 10000) > 0.8}
        />
        <Meter
          label={`Spend today · $${((meters?.spend_today_cents ?? 0) / 100).toFixed(2)}`}
          value={Math.min((meters?.spend_today_cents ?? 0) / 500, 1)}
        />
        <Meter
          label={`Credits burned · ${meters?.credits.burned_today ?? 0} / balance ${meters?.credits.balance ?? 0}`}
          value={
            meters && meters.credits.balance > 0
              ? Math.min(meters.credits.burned_today / meters.credits.balance, 1)
              : 0
          }
        />
        {meters?.local ? (
          <Meter
            label={`VRAM · ${(meters.local.vram_used_mb / 1024).toFixed(1)} / ${(meters.local.vram_total_mb / 1024).toFixed(1)} GB`}
            value={meters.local.vram_used_mb / Math.max(meters.local.vram_total_mb, 1)}
            hot
          />
        ) : (
          <Meter label="Local GPU · cloud mode" value={0} />
        )}
      </div>

      {/* THE DIAGRAM */}
      <div className="flex items-center justify-between py-4">
        <Wire tone="dim">live pipeline</Wire>
        <div className="flex gap-4">
          {followTrace ? (
            <button onClick={() => { setFollowTrace(null); setTraceEvents([]); }}>
              <Wire tone="human">following {followTrace.slice(0, 8)} · clear</Wire>
            </button>
          ) : null}
          <button onClick={() => setPaused((p) => !p)}>
            <Wire tone={paused ? "reject" : "dim"}>{paused ? "▶ resume" : "❚❚ pause"}</Wire>
          </button>
          <button
            onClick={() => {
              const blob = new Blob([JSON.stringify(events, null, 2)], {
                type: "application/json",
              });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "wire-events.json";
              a.click();
            }}
          >
            <Wire tone="dim">export json</Wire>
          </button>
        </div>
      </div>

      <div className="flex items-center gap-1 overflow-x-auto pb-6">
        {STAGES.map((stage, i) => (
          <StageNode
            key={stage}
            stage={stage}
            count={
              stage === "you"
                ? counters.rank ?? 0
                : (summary[stage]?.events ?? 0) + (counters[stage] ?? 0)
            }
            active={Date.now() - (pulses[stage] ?? 0) < 3000}
            failed={Date.now() - (failing[stage] ?? 0) < 6000}
            selected={selected === stage}
            hasFlowIn={i > 0 && Date.now() - (pulses[stage] ?? 0) < 3000}
            onClick={() => setSelected(selected === stage ? null : stage)}
          />
        ))}
      </div>

      {/* INSPECTION */}
      {selected && selected !== "you" ? (
        <Print className="p-6" caption={`STAGE · ${selected.toUpperCase()} — LAST ${stageEvents.length} EVENTS`}>
          {stageEvents.length === 0 ? (
            <p className="py-6 text-center font-mono text-[12px] text-ink-soft">
              Nothing through this stage since you opened the room. Dead screen,
              dead pipeline — that&apos;s honesty, not a bug.
            </p>
          ) : (
            <ul className="divide-y divide-ink/10">
              {stageEvents.map((e) => (
                <EventRow key={e.id} event={e} onFollow={() => void follow(e.trace_id)} />
              ))}
            </ul>
          )}
        </Print>
      ) : null}

      {selected === "you" ? (
        <Print className="p-6" caption="STAGE · YOU — THE ONE THE MACHINE CANNOT DO">
          <p className="py-4 text-body text-ink-soft">
            This stage is you: the swipe and the take. Everything upstream
            compresses the news so you can act on it; everything downstream
            amplifies what you decided. The machine waits here.
          </p>
        </Print>
      ) : null}

      {followTrace && traceEvents.length ? (
        <div className="mt-6 rounded-chrome bg-selenium p-6">
          <Wire tone="hot">one item&apos;s journey · trace {followTrace.slice(0, 12)}</Wire>
          <ol className="mt-4 space-y-2">
            {traceEvents.map((e) => (
              <li key={e.id} className="flex items-baseline gap-3 font-mono text-[12px]">
                <span className={e.status === "failed" ? "text-spike" : "text-fixer-hot"}>●</span>
                <span className="text-silver">{e.stage}</span>
                <span className="text-silver-dim">
                  {e.duration_ms ? `${(e.duration_ms / 1000).toFixed(2)}s` : ""}
                  {typeof e.payload.cost_cents === "number"
                    ? ` · $${(e.payload.cost_cents / 100).toFixed(4)}`
                    : ""}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

function Meter({
  label,
  value,
  danger = false,
  hot = false,
}: {
  label: string;
  value: number;
  danger?: boolean;
  hot?: boolean;
}) {
  const clamped = Math.min(Math.max(value, 0), 1);
  return (
    <div>
      <div className="h-[6px] overflow-hidden rounded-print bg-graphite-2">
        <div
          className={`h-full rounded-print transition-all duration-700 ${
            danger ? "bg-spike" : hot ? "bg-fixer-hot" : "bg-fixer"
          }`}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
      <p className="wire-label mt-2 text-silver-dim/70">{label}</p>
    </div>
  );
}

function StageNode({
  stage,
  count,
  active,
  failed,
  selected,
  hasFlowIn,
  onClick,
}: {
  stage: StageName;
  count: number;
  active: boolean;
  failed: boolean;
  selected: boolean;
  hasFlowIn: boolean;
  onClick: () => void;
}) {
  const isHuman = stage === "you";
  return (
    <>
      {stage !== "fetch" ? (
        <div className="relative h-px w-8 shrink-0 bg-fixer/40">
          {hasFlowIn ? (
            <span
              className="absolute top-1/2 h-[3px] w-[3px] -translate-y-1/2 rounded-full bg-fixer-hot"
              style={{ animation: "travel 900ms linear infinite" }}
            />
          ) : null}
          <style jsx>{`
            @keyframes travel {
              from { left: 0; opacity: 1; }
              to { left: 100%; opacity: 0.4; }
            }
          `}</style>
        </div>
      ) : null}
      <button
        onClick={onClick}
        className={`shrink-0 px-5 py-4 transition-colors ${
          isHuman
            ? "rounded-full border border-safelight/60 bg-[#241D1B]"
            : "rounded-chrome bg-selenium hover:bg-selenium-2"
        } ${selected ? "outline outline-1 outline-fixer-hot" : ""} ${
          failed ? "animate-pulse outline outline-1 outline-spike" : ""
        }`}
        style={{ opacity: active || isHuman ? 1 : 0.66 }}
      >
        <Wire tone={isHuman ? "human" : active ? "hot" : "dim"}>{stage}</Wire>
        <div className={`mt-1 font-mono text-[13px] ${isHuman ? "text-safelight" : "text-fixer-hot"}`}>
          {count}
        </div>
      </button>
    </>
  );
}

function EventRow({
  event,
  onFollow,
}: {
  event: PipelineEvent;
  onFollow: () => void;
}) {
  const [open, setOpen] = useState(false);
  const p = event.payload;
  const isModelCall = typeof p.provider === "string";
  return (
    <li className="py-2">
      <div className="flex items-baseline gap-3 font-mono text-[11.5px]">
        <span className="text-ink-soft">
          {new Date(event.created_at).toLocaleTimeString()}
        </span>
        {isModelCall ? <span className="text-[#4A4270]">{String(p.model ?? p.provider)}</span> : null}
        <span className={event.status === "failed" ? "text-spike" : "text-ink"}>
          {event.entity_type} {event.entity_id.slice(0, 8)}
        </span>
        <span className="text-ink-soft">
          {event.duration_ms ? `${(event.duration_ms / 1000).toFixed(2)}s` : ""}
          {typeof p.cost_cents === "number" ? ` · $${(Number(p.cost_cents) / 100).toFixed(4)}` : ""}
          {typeof p.input_tokens === "number" ? ` · ${String(p.input_tokens)} in / ${String(p.output_tokens ?? 0)} out` : ""}
          {typeof p.items_fetched === "number" ? ` · ${String(p.items_fetched)} fetched, ${String(p.items_new)} new` : ""}
          {typeof p.estimate_cents === "number" && typeof p.cost_cents === "number" &&
          Number(p.cost_cents) > Number(p.estimate_cents) * 1.2 ? (
            <span className="text-spike"> · over estimate</span>
          ) : null}
        </span>
        <span className="ml-auto flex gap-3">
          {isModelCall ? (
            <button className="text-fixer" onClick={() => setOpen((o) => !o)}>
              {open ? "▾ close" : "▸ prompt/response"}
            </button>
          ) : null}
          <button className="text-safelight" onClick={onFollow}>
            follow
          </button>
        </span>
      </div>
      {open && isModelCall ? (
        <div className="mt-2 space-y-2">
          {(["prompt", "response"] as const).map((key) =>
            typeof p[key] === "string" ? (
              <div key={key} className="rounded-print bg-ink/5 p-3">
                <div className="mb-1 flex justify-between">
                  <span className="wire-label text-fixer">{key}</span>
                  <button
                    className="wire-label text-safelight"
                    onClick={() => void navigator.clipboard.writeText(String(p[key]))}
                  >
                    copy
                  </button>
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-ink-soft">
                  {String(p[key])}
                </pre>
              </div>
            ) : null,
          )}
        </div>
      ) : null}
    </li>
  );
}
