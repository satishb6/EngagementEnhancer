"use client";

/**
 * Take capture. Every interaction here should cost under 5 seconds:
 * three tappable suggested stances (Redaction 10 — obviously machine-made),
 * an editor whose grade animates 10 → 100 as the user makes it theirs,
 * hold-to-record voice with live transcription, and skip always available.
 */

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, type Keep, type Suggestion } from "@/lib/api";
import {
  ChromeButton,
  Develop,
  Print,
  RedactionText,
  SafelightButton,
  springs,
  Wire,
} from "@/components/ui/primitives";

export default function DarkroomPage() {
  const [keeps, setKeeps] = useState<Keep[]>([]);
  const [index, setIndex] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [sheetReady, setSheetReady] = useState<Record<string, string>>({});

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.keeps();
        setKeeps(res.keeps);
        const ready: Record<string, string> = {};
        for (const k of res.keeps) {
          if (k.take) ready[k.briefing.id] = k.take.id;
        }
        setSheetReady(ready);
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

  const advance = useCallback(() => {
    setIndex((i) => Math.min(i + 1, keeps.length));
  }, [keeps.length]);

  if (!loaded) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Wire tone="machine">collecting your keeps…</Wire>
      </div>
    );
  }

  if (!keeps.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-32">
        <RedactionText grade={35} className="text-display">
          Nothing kept yet.
        </RedactionText>
        <p className="text-body text-silver-dim">
          Swipe right on the wire and the keepers land here.
        </p>
        <Link href="/wire">
          <SafelightButton>To the wire</SafelightButton>
        </Link>
      </div>
    );
  }

  const keep = keeps[index];
  const doneCount = Object.keys(sheetReady).length;

  if (!keep) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-32">
        <RedactionText grade={100} className="text-display">
          {doneCount} takes on the record.
        </RedactionText>
        <p className="text-body text-silver-dim">
          The machine is making your prints. Pick the keepers on each contact sheet.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-3">
          {keeps.filter((k) => sheetReady[k.briefing.id]).map((k) => (
            <Link key={k.briefing.id} href={`/darkroom/${sheetReady[k.briefing.id]}/sheet`}>
              <ChromeButton>{k.briefing.headline.slice(0, 32)}…</ChromeButton>
            </Link>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <Wire tone="dim">
          take {index + 1} of {keeps.length}
        </Wire>
        <div className="flex gap-4">
          <button onClick={() => setIndex((i) => Math.max(0, i - 1))}>
            <Wire tone="dim">← prev</Wire>
          </button>
          <button onClick={advance}>
            <Wire tone="dim">skip →</Wire>
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={keep.briefing.id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={springs.settle}
        >
          <TakeEditor
            keep={keep}
            onDone={(takeId) => {
              setSheetReady((m) => ({ ...m, [keep.briefing.id]: takeId }));
              advance();
            }}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function TakeEditor({
  keep,
  onDone,
}: {
  keep: Keep;
  onDone: (takeId: string) => void;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [text, setText] = useState(keep.take?.text ?? "");
  const [startedFrom, setStartedFrom] = useState("");
  const [stance, setStance] = useState(keep.take?.stance ?? "");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.suggest(keep.briefing.id);
        setSuggestions(res.suggestions);
      } catch {
        setSuggestions([]);
      }
    })();
  }, [keep.briefing.id]);

  // grade progress: how far has the user made this text theirs
  const editRatio = startedFrom
    ? 1 - similarity(startedFrom, text)
    : text.length > 0
      ? 1
      : 0;
  const progress = Math.min(editRatio / 0.3, 1);

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.createTake({
        briefing_id: keep.briefing.id,
        feed_item_id: keep.feed_item_id,
        text: text.trim(),
        suggested_text: startedFrom,
        stance,
      });
      onDone(res.take_id);
    } finally {
      setBusy(false);
    }
  };

  const record = async () => {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream);
    recorder.current = mr;
    chunks.current = [];
    mr.ondataavailable = (e) => chunks.current.push(e.data);
    mr.onstop = async () => {
      setRecording(false);
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks.current, { type: "audio/webm" });
      const form = new FormData();
      form.append("briefing_id", keep.briefing.id);
      form.append("audio", blob, "take.webm");
      const res = await fetch("/api/wire/take/audio", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      if (res.ok) {
        const data = (await res.json()) as { transcript: string };
        setText(data.transcript);
        setStartedFrom("");
      }
    };
    mr.start();
    setRecording(true);
  };

  return (
    <div>
      <Develop>
        <Print
          className="p-8"
          caption={`${keep.briefing.source_links.length || 1} SOURCES · CLUSTER ${keep.briefing.cluster_id.slice(0, 4)}`}
        >
          <h2 className="text-briefing text-ink">
            <RedactionText grade={35}>{keep.briefing.headline}</RedactionText>
          </h2>
          <p className="mt-4 text-body text-ink-soft">{keep.briefing.body}</p>
        </Print>
      </Develop>

      <div className="mt-8 grid gap-3 sm:grid-cols-3">
        {suggestions.map((s) => (
          <motion.button
            key={s.stance + s.text.slice(0, 12)}
            whileTap={{ scale: 0.97 }}
            transition={springs.snap}
            onClick={() => {
              setText(s.text);
              setStartedFrom(s.text);
              setStance(s.stance);
            }}
            className="rounded-chrome bg-selenium p-4 text-left hover:bg-selenium-2"
          >
            <Wire tone="machine">{s.stance}</Wire>
            <p className="mt-2 text-label text-silver-dim">
              <RedactionText grade={10}>{s.text}</RedactionText>
            </p>
          </motion.button>
        ))}
      </div>

      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <Wire tone={progress >= 1 ? "human" : "machine"}>
            {progress >= 1 ? "yours" : startedFrom ? "make it yours" : "your take"}
          </Wire>
          <button onClick={() => void record()}>
            <Wire tone={recording ? "reject" : "dim"}>
              {recording ? "■ stop — transcribing" : "● hold forth (voice)"}
            </Wire>
          </button>
        </div>
        <div className="rounded-chrome bg-selenium p-1">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            placeholder="One or two sharp sentences. Or tap a stance above and bend it."
            className="w-full resize-none rounded-chrome bg-selenium px-4 py-3 text-body text-silver outline-none placeholder:text-silver-dim/40"
            style={{
              opacity: 0.85 + 0.15 * progress,
              filter: `contrast(${1.25 - 0.25 * progress})`,
            }}
          />
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-3">
        <SafelightButton big onClick={() => void submit()} disabled={busy || !text.trim()}>
          {busy ? "Developing" : "Develop the prints"}
        </SafelightButton>
      </div>
    </div>
  );
}

/** cheap char-bigram similarity — mirrors the server's diff intent */
function similarity(a: string, b: string): number {
  if (!a.length || !b.length) return 0;
  const grams = (s: string) => {
    const set = new Set<string>();
    for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
    return set;
  };
  const ga = grams(a);
  const gb = grams(b);
  let hit = 0;
  ga.forEach((g) => {
    if (gb.has(g)) hit += 1;
  });
  return (2 * hit) / (ga.size + gb.size);
}
