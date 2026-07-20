"use client";

/** Every primitive in every state — the design-system checkroom. */

import { useState } from "react";
import {
  ChromeButton,
  Develop,
  Print,
  RedactionText,
  SafelightButton,
  Wire,
} from "@/components/ui/primitives";

export default function Gallery() {
  const [progress, setProgress] = useState(0);
  return (
    <div className="mx-auto max-w-4xl space-y-14 px-6 py-12">
      <section>
        <Wire tone="dim">type — three faces, three jobs</Wire>
        <div className="mt-4 space-y-4">
          <p className="text-display-xl"><RedactionText grade={35}>Display XL, Redaction 35</RedactionText></p>
          <p className="text-briefing"><RedactionText grade={35}>Briefing size carries the news itself.</RedactionText></p>
          <p className="text-body">Body in Instrument Sans, tight tracking, 1.6 leading — the interface voice.</p>
          <p className="text-label">Label 14 — buttons say what happens.</p>
          <Wire>Wire 11 · uppercase · tracked · the machine measured this</Wire>
        </div>
      </section>

      <section>
        <Wire tone="dim">redaction grade = provenance</Wire>
        <div className="mt-4 space-y-3">
          <p className="text-briefing"><RedactionText grade={10}>Grade 10 — machine-made, before you touched it.</RedactionText></p>
          <p className="text-briefing"><RedactionText grade={35}>Grade 35 — journalism, processed but faithful.</RedactionText></p>
          <p className="text-briefing"><RedactionText grade={100}>Grade 100 — yours. You wrote this.</RedactionText></p>
          <div className="rounded-chrome bg-selenium p-4">
            <input
              type="range"
              min={0}
              max={100}
              value={progress}
              onChange={(e) => setProgress(Number(e.target.value))}
              className="w-56 accent-[#FF8A3D]"
            />
            <p className="mt-2 text-briefing">
              <RedactionText progress={progress / 100}>
                The grade animates 10 → 100 as you edit.
              </RedactionText>
            </p>
          </div>
        </div>
      </section>

      <section>
        <Wire tone="dim">material — print vs chrome</Wire>
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          <Develop>
            <Print className="p-6" caption="4 SOURCES · 41M AGO · CLUSTER 8F2A">
              <p className="text-briefing text-ink">
                <RedactionText grade={35}>A print is an object.</RedactionText>
              </p>
              <p className="mt-3 text-[14px] text-ink-soft">
                Cut corners, top-edge highlight, real shadow, caption rail. It
                develops in; it never fades in.
              </p>
            </Print>
          </Develop>
          <div className="chrome-surface p-6">
            <Wire tone="machine">machine chrome</Wire>
            <p className="mt-3 text-[14px] text-silver-dim">
              Separated by tone, not border. No shadow — elevation belongs to
              prints.
            </p>
            <div className="mt-4 flex gap-3">
              <SafelightButton>Post it</SafelightButton>
              <ChromeButton>Not now</ChromeButton>
            </div>
          </div>
        </div>
      </section>

      <section>
        <Wire tone="dim">agency — colour semantics</Wire>
        <div className="mt-4 flex flex-wrap gap-4">
          <span className="rounded-chrome bg-safelight px-4 py-2 text-label font-semibold text-ink">safelight = you</span>
          <span className="rounded-chrome bg-fixer px-4 py-2 text-label text-silver">fixer = machine</span>
          <span className="rounded-chrome bg-fixer-hot px-4 py-2 text-label text-ink">fixer-hot = machine, now</span>
          <span className="rounded-chrome bg-spike px-4 py-2 text-label text-silver">spike = reject</span>
        </div>
      </section>
    </div>
  );
}
