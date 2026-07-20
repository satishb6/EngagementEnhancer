"use client";

/**
 * Dashboard — hand-rolled SVG charts, no library defaults. Sparse gridlines
 * in graphite, machine series in fixer, user-driven metrics in safelight.
 * Voice match is THE metric: falling edit distance, shown as a percentage.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RedactionText, Wire } from "@/components/ui/primitives";

export default function DashboardPage() {
  const [voice, setVoice] = useState<Awaited<ReturnType<typeof api.voiceMatch>> | null>(null);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof api.summary>> | null>(null);
  const [balance, setBalance] = useState<Awaited<ReturnType<typeof api.balance>> | null>(null);
  const [queue, setQueue] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    void (async () => {
      try {
        const [v, s, b] = await Promise.all([
          api.voiceMatch(),
          api.summary(24 * 60),
          api.balance(),
        ]);
        setVoice(v);
        setSummary(s);
        setBalance(b);
        if (b.can_publish) setQueue(await api.publishQueue());
      } catch {
        /* shell handles auth */
      }
    })();
  }, []);

  const posted = queue.filter((q) => q.status === "posted").length;
  const briefed = summary?.stages.brief?.events ?? 0;
  const generated = summary?.stages.generate?.events ?? 0;
  const costCents = Object.values(summary?.stages ?? {}).reduce(
    (acc, s) => acc + s.cost_cents,
    0,
  );

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <Wire tone="dim">the numbers, honestly</Wire>
      <h1 className="mb-10 mt-1 text-display">
        <RedactionText grade={35}>Dashboard</RedactionText>
      </h1>

      <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
        <Stat label="posts published" value={String(posted)} human />
        <Stat label="briefings processed · 24h" value={String(briefed)} />
        <Stat label="generations · 24h" value={String(generated)} />
        <Stat
          label="cost · 24h"
          value={`$${(costCents / 100).toFixed(2)}`}
        />
      </div>

      <section className="mt-14">
        <div className="flex items-baseline justify-between">
          <Wire tone="human">voice match</Wire>
          <span className="font-mono text-[26px] text-safelight">
            {voice?.current != null ? `${voice.current.toFixed(0)}%` : "—"}
          </span>
        </div>
        <p className="mb-4 mt-1 max-w-lg text-label text-silver-dim">
          How little you have to edit a suggested take before posting it. If the
          learning works, this climbs week over week. If it doesn&apos;t, you&apos;ll
          see that here too.
        </p>
        <VoiceChart series={voice?.series ?? []} />
      </section>

      <section className="mt-14">
        <Wire tone="machine">pipeline · last 24h</Wire>
        <StageBars stages={summary?.stages ?? {}} />
      </section>

      <section className="mt-14">
        <Wire tone="machine">cost transparency</Wire>
        <p className="mt-1 max-w-lg text-label text-silver-dim">
          Every generation is estimated before it runs and the actual lands next
          to it. Tier: <span className="text-silver">{balance?.tier}</span> ·
          balance <span className="text-safelight">{balance?.balance}</span> credits.
          The full per-call record lives in the Wire Room.
        </p>
      </section>
    </div>
  );
}

function Stat({ label, value, human = false }: { label: string; value: string; human?: boolean }) {
  return (
    <div className="rounded-chrome bg-selenium p-5">
      <p className={`font-display text-[30px] leading-none ${human ? "text-safelight" : "text-silver"}`}>
        {value}
      </p>
      <p className="wire-label mt-2 text-silver-dim/70">{label}</p>
    </div>
  );
}

function VoiceChart({
  series,
}: {
  series: Array<{ week: string; voice_match_pct: number; takes: number }>;
}) {
  const w = 720;
  const h = 160;
  if (!series.length) {
    return (
      <div className="flex h-40 items-center rounded-chrome bg-graphite-2 px-6">
        <p className="text-label text-silver-dim">
          Write takes from suggestions and the trend appears here — it needs a
          week or two of you.
        </p>
      </div>
    );
  }
  const xs = series.map((_, i) => (i / Math.max(series.length - 1, 1)) * (w - 60) + 40);
  const ys = series.map((s) => h - 24 - (s.voice_match_pct / 100) * (h - 48));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-chrome bg-graphite-2">
      {[25, 50, 75].map((pct) => {
        const y = h - 24 - (pct / 100) * (h - 48);
        return (
          <g key={pct}>
            <line x1={40} x2={w - 20} y1={y} y2={y} stroke="#1E262F" strokeWidth={1} />
            <text x={8} y={y + 3} fill="#B5AFA2" fontSize={9} fontFamily="Martian Mono">
              {pct}%
            </text>
          </g>
        );
      })}
      <path d={path} fill="none" stroke="#FF8A3D" strokeWidth={2} strokeLinecap="round" />
      {xs.map((x, i) => (
        <circle key={i} cx={x} cy={ys[i]} r={3} fill="#FF8A3D" />
      ))}
      {xs.map((x, i) => (
        <text
          key={i}
          x={x}
          y={h - 8}
          fill="#B5AFA2"
          fontSize={8}
          fontFamily="Martian Mono"
          textAnchor="middle"
        >
          {series[i].week.slice(5)}
        </text>
      ))}
    </svg>
  );
}

function StageBars({
  stages,
}: {
  stages: Record<string, { events: number; p95_ms: number | null; error_rate: number; cost_cents: number }>;
}) {
  const entries = Object.entries(stages);
  if (!entries.length) {
    return (
      <div className="mt-3 flex h-24 items-center rounded-chrome bg-graphite-2 px-6">
        <p className="text-label text-silver-dim">Quiet pipeline. Run an ingest cycle.</p>
      </div>
    );
  }
  const max = Math.max(...entries.map(([, s]) => s.events), 1);
  return (
    <div className="mt-3 space-y-2 rounded-chrome bg-graphite-2 p-5">
      {entries.map(([stage, s]) => (
        <div key={stage} className="flex items-center gap-3">
          <span className="wire-label w-20 text-silver-dim">{stage}</span>
          <div className="h-[6px] flex-1 overflow-hidden rounded-print bg-selenium">
            <div
              className={`h-full ${s.error_rate > 0.1 ? "bg-spike" : "bg-fixer"}`}
              style={{ width: `${(s.events / max) * 100}%` }}
            />
          </div>
          <span className="w-40 text-right font-mono text-[11px] text-silver-dim">
            {s.events} · p95 {s.p95_ms ? `${(s.p95_ms / 1000).toFixed(1)}s` : "—"} ·
            ${(s.cost_cents / 100).toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  );
}
