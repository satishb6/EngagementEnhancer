"use client";

/**
 * The Contact Sheet — the version picker as a photographic contact sheet.
 * One silver print holding a grid of numbered frames; sprocket holes drawn,
 * not imaged; selection draws a grease-pencil circle in safelight with a
 * hand-drawn wobble, stroked on over 300ms. Long-press opens generation
 * metadata. Below: the selected set and one safelight action.
 */

import { motion } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Artifact, type Sheet } from "@/lib/api";
import {
  ChromeButton,
  Print,
  RedactionText,
  SafelightButton,
  Wire,
} from "@/components/ui/primitives";

export default function SheetPage() {
  const { takeId } = useParams<{ takeId: string }>();
  const router = useRouter();
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [inspecting, setInspecting] = useState<Artifact | null>(null);
  const [videoConfirm, setVideoConfirm] = useState<{ credits: number } | null>(null);

  const load = useCallback(async () => {
    setSheet(await api.sheet(takeId));
  }, [takeId]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  const frames = useMemo(() => sheet?.artifacts ?? [], [sheet]);
  const running = (sheet?.jobs ?? []).filter(
    (j) => j.state === "queued" || j.state === "running",
  );

  const select = async (artifact: Artifact) => {
    setPicked((p) => ({ ...p, [artifact.content_type]: artifact.id }));
    try {
      await api.pick(artifact.id, "x");
    } catch {
      /* the circle is still drawn; the pick retries on publish */
    }
  };

  const requestVideo = async (longForm: boolean, confirmCredits?: number) => {
    const res = await api.requestVideo({
      take_id: takeId,
      long_form: longForm,
      duration_s: longForm ? 90 : 20,
      confirm_credits: confirmCredits,
    });
    if (res.confirmation_required) {
      setVideoConfirm({ credits: Number(res.credits) });
    } else {
      setVideoConfirm(null);
      void load();
    }
  };

  if (!sheet) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Wire tone="machine">printing the contact sheet…</Wire>
      </div>
    );
  }

  const selectedIds = new Set(Object.values(picked));

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <Wire tone="dim">contact sheet · take {takeId.slice(0, 8)}</Wire>
        <button onClick={() => router.push("/darkroom")}>
          <Wire tone="dim">← darkroom</Wire>
        </button>
      </div>

      <Print className="relative px-10 py-8">
        <SprocketHoles edge="top" />
        <div className="grid grid-cols-2 gap-6 py-6 sm:grid-cols-3">
          {frames.map((artifact, i) => (
            <SheetFrame
              key={artifact.id}
              index={i + 1}
              artifact={artifact}
              selected={selectedIds.has(artifact.id)}
              onSelect={() => void select(artifact)}
              onInspect={() => setInspecting(artifact)}
            />
          ))}
          {running.map((job, i) => (
            <div
              key={job.id}
              className="flex aspect-square flex-col items-center justify-center rounded-print border border-dashed border-fixer/40"
            >
              <Wire tone="hot">frame {frames.length + i + 1}</Wire>
              <Wire tone="machine" className="mt-2">
                {job.content_type} developing…
              </Wire>
            </div>
          ))}
          {sheet.video_offers.map((offer) => (
            <button
              key={offer.content_type}
              onClick={() =>
                void requestVideo(offer.gated, videoConfirm ? videoConfirm.credits : undefined)
              }
              className="relative flex aspect-square flex-col items-center justify-center overflow-hidden rounded-print border border-ink/20"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(12,15,19,0.08) 6px, rgba(12,15,19,0.08) 7px), repeating-linear-gradient(-45deg, transparent, transparent 6px, rgba(12,15,19,0.08) 6px, rgba(12,15,19,0.08) 7px)",
              }}
            >
              <Wire tone="machine">{offer.content_type.replace("_", " ")}</Wire>
              <span className="mt-2 font-mono text-label text-ink-soft">
                {offer.credits} credits
              </span>
              {offer.gated ? (
                <Wire tone="reject" className="mt-1">
                  confirms cost first
                </Wire>
              ) : null}
            </button>
          ))}
        </div>
        <SprocketHoles edge="bottom" />
      </Print>

      {videoConfirm ? (
        <div className="mt-6 rounded-chrome bg-selenium p-6">
          <p className="text-body text-silver">
            Long-form video costs{" "}
            <span className="font-mono text-safelight">{videoConfirm.credits} credits</span>.
            A storyboard renders first for your approval — nothing films until you say so.
          </p>
          <div className="mt-4 flex gap-3">
            <SafelightButton onClick={() => void requestVideo(true, videoConfirm.credits)}>
              Spend {videoConfirm.credits} credits
            </SafelightButton>
            <ChromeButton onClick={() => setVideoConfirm(null)}>Not now</ChromeButton>
          </div>
        </div>
      ) : null}

      <div className="mt-8 flex items-center justify-between">
        <div className="flex gap-3">
          {Object.entries(picked).map(([type, id]) => (
            <Wire key={id} tone="human">
              {type} ✓
            </Wire>
          ))}
          {!Object.keys(picked).length ? (
            <Wire tone="dim">circle the keepers</Wire>
          ) : null}
        </div>
        <SafelightButton
          big
          disabled={!Object.keys(picked).length}
          onClick={() =>
            router.push(
              `/prints?selected=${encodeURIComponent(Object.values(picked).join(","))}`,
            )
          }
        >
          Make the print
        </SafelightButton>
      </div>

      {inspecting ? (
        <FrameInspector artifact={inspecting} onClose={() => setInspecting(null)} />
      ) : null}
    </div>
  );
}

function SheetFrame({
  index,
  artifact,
  selected,
  onSelect,
  onInspect,
}: {
  index: number;
  artifact: Artifact;
  selected: boolean;
  onSelect: () => void;
  onInspect: () => void;
}) {
  const pressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  return (
    <div className="relative">
      <span className="wire-label absolute -left-7 top-1 text-fixer">
        {String(index).padStart(2, "0")}
      </span>
      <button
        className="relative block w-full overflow-hidden rounded-print border border-ink/15 bg-graphite/5 text-left"
        onClick={onSelect}
        onPointerDown={() => {
          pressTimer.current = setTimeout(onInspect, 550);
        }}
        onPointerUp={() => pressTimer.current && clearTimeout(pressTimer.current)}
        onPointerLeave={() => pressTimer.current && clearTimeout(pressTimer.current)}
      >
        <div className="aspect-square overflow-hidden p-3">
          {artifact.content_type === "text" ? (
            <p className="text-[11px] leading-relaxed text-ink-soft">
              <RedactionText grade={10}>{artifact.text_content.slice(0, 360)}</RedactionText>
            </p>
          ) : artifact.storage_uri.startsWith("http") ||
            artifact.storage_uri.startsWith("/") ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={artifact.storage_uri}
              alt={`frame ${index}`}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Wire tone="machine">{artifact.content_type}</Wire>
            </div>
          )}
          {artifact.duration_ms ? (
            <span className="wire-label absolute bottom-2 right-2 rounded-print bg-ink/70 px-1.5 py-0.5 text-silver">
              {Math.round(artifact.duration_ms / 1000)}s
            </span>
          ) : null}
        </div>
        {selected ? <GreasePencilCircle /> : null}
      </button>
    </div>
  );
}

/** Safelight grease-pencil circle, stroked on over 300ms with a hand wobble. */
function GreasePencilCircle() {
  const path = useMemo(() => {
    const pts: string[] = [];
    const steps = 26;
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2 - Math.PI / 2;
      const wobble = 46 + Math.sin(i * 2.7) * 2.2 + Math.cos(i * 1.3) * 1.6;
      const x = 50 + wobble * Math.cos(angle) * 0.98;
      const y = 50 + wobble * Math.sin(angle) * 0.92;
      pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return pts.join(" ");
  }, []);

  return (
    <svg
      viewBox="0 0 100 100"
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ overflow: "visible" }}
    >
      <motion.path
        d={path}
        fill="none"
        stroke="#FF8A3D"
        strokeWidth={3.2}
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0.9 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease: [0.3, 0.7, 0.4, 1] }}
        style={{ filter: "url(#grease)" }}
      />
      <defs>
        <filter id="grease">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="1.6" />
        </filter>
      </defs>
    </svg>
  );
}

function SprocketHoles({ edge }: { edge: "top" | "bottom" }) {
  return (
    <div
      className={`absolute inset-x-8 flex justify-between ${
        edge === "top" ? "top-2" : "bottom-2"
      }`}
      aria-hidden
    >
      {Array.from({ length: 14 }).map((_, i) => (
        <span key={i} className="h-2 w-3 rounded-[2px] bg-ink/12" />
      ))}
    </div>
  );
}

function FrameInspector({
  artifact,
  onClose,
}: {
  artifact: Artifact;
  onClose: () => void;
}) {
  const meta = artifact.meta as Record<string, unknown>;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/85 p-8"
      onClick={onClose}
    >
      <Print className="max-h-full w-full max-w-2xl overflow-auto p-8" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <Wire tone="machine">generation record</Wire>
          <button onClick={onClose}>
            <Wire tone="dim">close</Wire>
          </button>
        </div>
        {artifact.text_content ? (
          <p className="mb-6 text-body text-ink">{artifact.text_content}</p>
        ) : artifact.storage_uri ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={artifact.storage_uri} alt="artifact" className="mb-6 w-full rounded-print" />
        ) : null}
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 font-mono text-[12px] text-ink-soft">
          {["provider", "model", "seed", "prompt", "synthesis"].map((key) =>
            meta[key] !== undefined ? (
              <div key={key} className="col-span-2 grid grid-cols-[90px_1fr] gap-2">
                <dt className="uppercase text-fixer">{key}</dt>
                <dd className="break-words">{String(meta[key])}</dd>
              </div>
            ) : null,
          )}
          <div className="col-span-2 grid grid-cols-[90px_1fr] gap-2">
            <dt className="uppercase text-fixer">created</dt>
            <dd>{artifact.created_at}</dd>
          </div>
        </dl>
      </Print>
    </div>
  );
}
