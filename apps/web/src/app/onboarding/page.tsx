"use client";

/**
 * First-run. The whole job is getting someone to their first swipe fast —
 * under 90 seconds on the cloud path. Interest selection IS a swipe deck of
 * topic cards, so the core gesture is learned before it matters.
 */

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { getToken } from "@/lib/api";
import {
  ChromeButton,
  Print,
  RedactionText,
  SafelightButton,
  springs,
  Wire,
} from "@/components/ui/primitives";

const TOPICS = [
  { key: "ai-policy", label: "AI & policy" },
  { key: "semiconductors", label: "Chips & compute" },
  { key: "climate-tech", label: "Climate tech" },
  { key: "space", label: "Space" },
  { key: "biotech", label: "Biotech" },
  { key: "markets", label: "Markets" },
];

const SOURCES: Record<string, string[]> = {
  "ai-policy": ["theverge.com", "arstechnica.com"],
  semiconductors: ["reuters.com", "bloomberg.com"],
  "climate-tech": ["nature.com", "apnews.com"],
  space: ["arstechnica.com", "reuters.com"],
  biotech: ["nature.com", "ft.com"],
  markets: ["ft.com", "bloomberg.com"],
};

export default function Onboarding() {
  const router = useRouter();
  const [step, setStep] = useState<"topics" | "sources" | "mode">("topics");
  const [remaining, setRemaining] = useState(TOPICS);
  const [liked, setLiked] = useState<string[]>([]);
  const [sources, setSources] = useState<Set<string>>(new Set());

  const decide = (keep: boolean) => {
    const [top, ...rest] = remaining;
    if (!top) return;
    if (keep) {
      setLiked((l) => [...l, top.key]);
      setSources((s) => {
        const next = new Set(s);
        for (const d of SOURCES[top.key] ?? []) next.add(d);
        return next;
      });
    }
    setRemaining(rest);
    if (!rest.length) setStep("sources");
  };

  const finish = async () => {
    if (!getToken()) {
      router.push("/signup");
      return;
    }
    // persist choices: domains become live RSS sources, topics tilt ranking
    try {
      await fetch("/api/wire/protocol/bootstrap", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ domains: [...sources], topics: liked }),
      });
    } catch {
      /* the deck still works from the shared pool */
    }
    router.push("/wire");
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 py-12">
      {step === "topics" ? (
        <>
          <Wire tone="dim">this is the whole gesture — learn it now</Wire>
          <h1 className="mb-8 mt-2 text-center text-display">
            <RedactionText grade={35}>Keep or toss?</RedactionText>
          </h1>
          <div className="relative h-64 w-full max-w-sm">
            {remaining.slice(0, 3).map((topic, i) => (
              <motion.div
                key={topic.key}
                className="absolute inset-0"
                style={{ zIndex: 10 - i }}
                initial={{ scale: 1 - i * 0.05, y: i * 14 }}
                animate={{ scale: 1 - i * 0.05, y: i * 14 }}
                transition={springs.settle}
                drag={i === 0 ? "x" : false}
                dragMomentum={false}
                onDragEnd={(_e, info) => {
                  if (Math.abs(info.offset.x) > 120) decide(info.offset.x > 0);
                }}
              >
                <Print className="flex h-64 cursor-grab items-center justify-center p-8 active:cursor-grabbing">
                  <span className="text-center font-display text-briefing text-ink">
                    {topic.label}
                  </span>
                </Print>
              </motion.div>
            ))}
          </div>
          <div className="mt-8 flex gap-6">
            <ChromeButton onClick={() => decide(false)}>← toss</ChromeButton>
            <SafelightButton onClick={() => decide(true)}>keep →</SafelightButton>
          </div>
          <button className="mt-6" onClick={() => setStep("sources")}>
            <Wire tone="dim">skip</Wire>
          </button>
        </>
      ) : null}

      {step === "sources" ? (
        <>
          <Wire tone="dim">derived from what you kept · edit freely</Wire>
          <h1 className="mb-8 mt-2 text-display">
            <RedactionText grade={35}>Your sources</RedactionText>
          </h1>
          <div className="flex max-w-md flex-wrap justify-center gap-3">
            {[...(sources.size ? sources : new Set(Object.values(SOURCES).flat()))].map(
              (domain) => (
                <button
                  key={domain}
                  onClick={() =>
                    setSources((s) => {
                      const next = new Set(s);
                      if (next.has(domain)) next.delete(domain);
                      else next.add(domain);
                      return next;
                    })
                  }
                  className={`rounded-full px-4 py-1.5 font-mono text-[12px] ${
                    sources.has(domain)
                      ? "bg-safelight text-ink"
                      : "border border-rule-strong text-silver-dim"
                  }`}
                >
                  {domain}
                </button>
              ),
            )}
          </div>
          <div className="mt-10 flex gap-4">
            <ChromeButton onClick={() => setStep("mode")}>skip</ChromeButton>
            <SafelightButton big onClick={() => setStep("mode")}>
              Looks right
            </SafelightButton>
          </div>
        </>
      ) : null}

      {step === "mode" ? (
        <>
          <Wire tone="dim">how the machine runs · changeable any time in Studio</Wire>
          <h1 className="mb-8 mt-2 text-display">
            <RedactionText grade={35}>Pick a mode</RedactionText>
          </h1>
          <div className="grid max-w-2xl gap-4 sm:grid-cols-3">
            <ModeCard
              title="Cloud"
              body="Default. The platform's models, metered in credits. Zero setup."
              onPick={finish}
              highlight
            />
            <ModeCard
              title="BYOK"
              body="Your own API keys, your own bills, our caps on top. For people who read invoices."
              onPick={finish}
            />
            <ModeCard
              title="Local"
              body="Your GPU. We'll probe your hardware in Studio and tell you honestly what it can run — video needs 16GB+."
              onPick={finish}
            />
          </div>
          <p className="mt-8 max-w-md text-center text-label text-silver-dim">
            {liked.length
              ? `Your first deck is seeding from ${liked.length} topics.`
              : "Your first deck seeds from the general wire."}
          </p>
        </>
      ) : null}
    </div>
  );
}

function ModeCard({
  title,
  body,
  onPick,
  highlight = false,
}: {
  title: string;
  body: string;
  onPick: () => void;
  highlight?: boolean;
}) {
  return (
    <button
      onClick={onPick}
      className={`rounded-chrome p-5 text-left transition-colors ${
        highlight
          ? "border border-safelight/50 bg-[#241D1B] hover:border-safelight"
          : "bg-selenium hover:bg-selenium-2"
      }`}
    >
      <p className={`text-body font-semibold ${highlight ? "text-safelight" : "text-silver"}`}>
        {title}
      </p>
      <p className="mt-2 text-label text-silver-dim">{body}</p>
    </button>
  );
}
