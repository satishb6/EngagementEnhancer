"use client";

/**
 * The swipe deck — the moment the app is judged on.
 *
 * Five cards visible, receding in z with scale and blur. Drag tilts the top
 * card (max 12°); past 30% width an edge glow appears (safelight right,
 * spike left); release past threshold flies the card off with carried
 * velocity and the next card rises on the settle spring. Swipes batch in
 * groups of five. Undo is one keystroke (u) or the persistent control.
 */

import {
  AnimatePresence,
  motion,
  useMotionValue,
  useTransform,
} from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type FeedItem } from "@/lib/api";
import {
  Develop,
  Print,
  RedactionText,
  springs,
  Wire,
} from "@/components/ui/primitives";

const THRESHOLD = 0.3; // fraction of card width

type Pending = {
  feed_item_id: string;
  direction: "left" | "right";
  dwell_ms: number;
  client_event_id: string;
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.max(1, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 60) return `${mins}M AGO`;
  const hours = Math.round(mins / 60);
  return hours < 24 ? `${hours}H AGO` : `${Math.round(hours / 24)}D AGO`;
}

export function SwipeDeck() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [done, setDone] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const pending = useRef<Pending[]>([]);
  const shownAt = useRef<number>(Date.now());

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.feed(0, 50);
        setItems(res.items);
        setTotal(res.total_today || res.items.length);
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

  const flush = useCallback(async (force = false) => {
    if (pending.current.length >= 5 || (force && pending.current.length)) {
      const batch = pending.current.splice(0, pending.current.length);
      try {
        await api.swipe(batch);
      } catch {
        pending.current.unshift(...batch); // retry with the next flush
      }
    }
  }, []);

  const swipe = useCallback(
    (direction: "left" | "right") => {
      setItems((current) => {
        const [top, ...rest] = current;
        if (!top) return current;
        pending.current.push({
          feed_item_id: top.feed_item_id,
          direction,
          dwell_ms: Date.now() - shownAt.current,
          client_event_id: `web-${top.feed_item_id.slice(0, 8)}-${Date.now()}`,
        });
        shownAt.current = Date.now();
        void flush();
        setDone((d) => d + 1);
        return rest;
      });
    },
    [flush],
  );

  const undo = useCallback(async () => {
    try {
      await flush(true);
      await api.undoSwipe();
      const res = await api.feed(0, 50);
      setItems(res.items);
      setDone((d) => Math.max(0, d - 1));
    } catch {
      /* nothing to undo */
    }
  }, [flush]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") swipe("right");
      if (e.key === "ArrowLeft") swipe("left");
      if (e.key === "u") void undo();
    };
    window.addEventListener("keydown", onKey);
    const flushTimer = setInterval(() => void flush(true), 4000);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearInterval(flushTimer);
    };
  }, [swipe, undo, flush]);

  if (!loaded) {
    return (
      <div className="flex h-full items-center justify-center">
        <Wire tone="machine">developing the deck…</Wire>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 py-24">
        <RedactionText grade={35} className="text-display">
          The wire is clear.
        </RedactionText>
        <p className="max-w-sm text-center text-body text-silver-dim">
          {done > 0
            ? `${done} briefings sorted. Your keeps are waiting in the Darkroom.`
            : "Nothing new on the wire yet. It refills as the day moves."}
        </p>
        {done > 0 ? (
          <a href="/darkroom" className="mt-4">
            <span className="rounded-chrome bg-safelight px-8 py-3 font-semibold text-ink">
              Into the Darkroom
            </span>
          </a>
        ) : null}
      </div>
    );
  }

  const stack = items.slice(0, 5);
  return (
    <div className="relative mx-auto flex h-[calc(100vh-140px)] max-w-xl flex-col items-center justify-center px-6">
      {/* particle field thins as the stack depletes */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ opacity: Math.min(items.length / 50, 1) * 0.5 }}
      >
        <ParticleField count={Math.min(items.length, 40)} />
      </div>

      <div className="relative h-[460px] w-full" style={{ perspective: 1200 }}>
        <AnimatePresence>
          {stack.map((item, i) => (
            <DeckCard
              key={item.feed_item_id}
              item={item}
              depth={i}
              onSwipe={swipe}
            />
          ))}
        </AnimatePresence>
      </div>

      <div className="mt-8 flex items-center gap-8">
        <button onClick={() => void undo()} aria-label="undo last swipe">
          <Wire tone="dim">undo (u)</Wire>
        </button>
        <Wire tone="dim">
          {done} / {Math.max(total, done + items.length)}
        </Wire>
        <Wire tone="dim">← toss · keep →</Wire>
      </div>
    </div>
  );
}

function DeckCard({
  item,
  depth,
  onSwipe,
}: {
  item: FeedItem;
  depth: number;
  onSwipe: (d: "left" | "right") => void;
}) {
  const x = useMotionValue(0);
  const rotateZ = useTransform(x, [-300, 300], [-12, 12]);
  const rotateY = useTransform(x, [-300, 300], [8, -8]);
  const keepGlow = useTransform(x, [60, 220], [0, 1]);
  const tossGlow = useTransform(x, [-220, -60], [1, 0]);
  const isTop = depth === 0;

  return (
    <motion.div
      className="absolute inset-0"
      style={{
        zIndex: 10 - depth,
        x: isTop ? x : 0,
        rotateZ: isTop ? rotateZ : 0,
        rotateY: isTop ? rotateY : 0,
      }}
      initial={{ scale: 1 - depth * 0.045, y: depth * 18, opacity: depth === 4 ? 0 : 1 }}
      animate={{
        scale: 1 - depth * 0.045,
        y: depth * 18,
        opacity: 1,
        filter: `blur(${depth * 1.1}px)`,
      }}
      exit={{
        x: x.get() > 0 ? 700 : -700,
        rotateZ: x.get() > 0 ? 24 : -24,
        opacity: 0,
        transition: { duration: 0.32 },
      }}
      transition={springs.settle}
      drag={isTop ? "x" : false}
      dragElastic={0.9}
      dragMomentum={false}
      onDragEnd={(_e, info) => {
        const width = 420;
        if (Math.abs(info.offset.x) > width * THRESHOLD || Math.abs(info.velocity.x) > 600) {
          onSwipe(info.offset.x > 0 ? "right" : "left");
        }
      }}
    >
      <Develop>
        <Print
          className={`flex h-[460px] flex-col p-8 ${isTop ? "cursor-grab shadow-lifted active:cursor-grabbing" : ""}`}
          caption={`${item.briefing.source_links.length || 1} SOURCES · ${timeAgo(item.briefing.published_at)} · CLUSTER ${item.briefing.cluster_id.slice(0, 4)}`}
        >
          {/* edge glows: safelight = keep, spike = toss */}
          {isTop ? (
            <>
              <motion.div
                className="pointer-events-none absolute inset-y-0 right-0 w-2 rounded-r-print bg-safelight"
                style={{ opacity: keepGlow }}
              />
              <motion.div
                className="pointer-events-none absolute inset-y-0 left-0 w-2 rounded-l-print bg-spike"
                style={{ opacity: tossGlow }}
              />
            </>
          ) : null}

          <h2 className="text-briefing text-ink">
            <RedactionText grade={35}>{item.briefing.headline}</RedactionText>
          </h2>
          <p className="mt-5 flex-1 text-body text-ink-soft">{item.briefing.body}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {item.briefing.source_links.slice(0, 4).map((link, li) => (
              <a
                key={`${link.domain}-${li}`}
                href={link.url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="wire-label rounded-print border border-ink/15 px-2 py-1 text-fixer hover:border-fixer"
              >
                {link.domain}
              </a>
            ))}
            {item.briefing.confidence === "low" ? (
              <span className="wire-label px-2 py-1 text-spike">contested</span>
            ) : null}
          </div>
        </Print>
      </Develop>
    </motion.div>
  );
}

function ParticleField({ count }: { count: number }) {
  // deterministic pseudo-random positions so SSR and client agree
  const dots = Array.from({ length: count }, (_, i) => {
    const seed = (i * 2654435761) % 997;
    return {
      left: `${(seed % 100)}%`,
      top: `${((seed * 7) % 100)}%`,
      size: 1 + (seed % 3),
      delay: (seed % 50) / 10,
    };
  });
  return (
    <div className="absolute inset-0 overflow-hidden">
      {dots.map((d, i) => (
        <span
          key={i}
          className="absolute rounded-full bg-fixer-hot"
          style={{
            left: d.left,
            top: d.top,
            width: d.size,
            height: d.size,
            opacity: 0.35,
            animation: `drift 14s ${d.delay}s linear infinite`,
          }}
        />
      ))}
      <style jsx>{`
        @keyframes drift {
          from { transform: translateY(0); }
          to { transform: translateY(-40px); }
        }
      `}</style>
    </div>
  );
}
