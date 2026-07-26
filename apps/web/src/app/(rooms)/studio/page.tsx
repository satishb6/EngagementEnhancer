"use client";

/**
 * Studio — protocols, mode, BYOK keys, learning resets. Cost transparency
 * lives here for BYOK users: trust is the entire product in that mode.
 */

import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import {
  ChromeButton,
  RedactionText,
  SafelightButton,
  Wire,
} from "@/components/ui/primitives";
import { useRouter } from "next/navigation";
import { EnginePanel } from "@/components/studio/EnginePanel";

type Caps = Awaited<ReturnType<typeof api.capabilities>>;

export default function StudioPage() {
  const router = useRouter();
  const [caps, setCaps] = useState<Caps | null>(null);
  const [balance, setBalance] = useState<Awaited<ReturnType<typeof api.balance>> | null>(null);
  const [byok, setByok] = useState<Array<Record<string, unknown>>>([]);
  const [notice, setNotice] = useState("");
  const [provider, setProvider] = useState("anthropic");
  const [key, setKey] = useState("");
  const [cap, setCap] = useState(500);

  const load = async () => {
    try {
      const [c, b] = await Promise.all([api.capabilities(), api.balance()]);
      setCaps(c);
      setBalance(b);
      const res = await fetch("/api/wire/billing/byok", {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setByok((await res.json()) as Array<Record<string, unknown>>);
    } catch {
      /* shell handles auth */
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const setMode = async (mode: "cloud" | "byok" | "local") => {
    const res = await fetch("/api/wire/system/mode", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ mode }),
    });
    if (res.ok) setNotice(`Mode set to ${mode}.`);
    else setNotice(((await res.json()) as { detail?: string }).detail ?? "Mode change failed.");
  };

  const saveKey = async () => {
    const res = await fetch("/api/wire/billing/byok", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ provider, api_key: key, daily_cap_cents: cap }),
    });
    if (res.ok) {
      setKey("");
      setNotice(`${provider} key stored (encrypted). It never comes back to this screen.`);
      void load();
    } else {
      setNotice("Key not accepted.");
    }
  };

  const resetLoop = async (loop: string) => {
    await api.resetLoop(loop);
    setNotice(`${loop} loop reset. The machine forgets; you start fresh.`);
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Wire tone="dim">the controls</Wire>
      <h1 className="mb-8 mt-1 text-display">
        <RedactionText grade={35}>Studio</RedactionText>
      </h1>

      {notice ? <p className="mb-6 text-label text-safelight">{notice}</p> : null}

      <section className="mb-10">
        <Wire tone="machine">tier &amp; credits</Wire>
        <div className="mt-3 flex items-center gap-6 rounded-chrome bg-selenium p-5">
          <div>
            <p className="font-mono text-[22px] text-safelight">{balance?.balance ?? 0}</p>
            <Wire tone="dim">credits</Wire>
          </div>
          <div>
            <p className="text-body text-silver">{balance?.tier ?? "free"}</p>
            <Wire tone="dim">
              {balance?.variant_count ?? 1} variants · {balance?.selections_per_day ?? 3} selections/day
            </Wire>
          </div>
        </div>
      </section>

      <EnginePanel onNotice={setNotice} />

      <ProtocolEditor onNotice={setNotice} />

      <section className="mb-10">
        <Wire tone="machine">mode</Wire>
        <p className="mt-1 text-label text-silver-dim">
          Cloud is the default. BYOK bills your own provider keys. Local runs on
          your GPU — the probe below is honest about what that means.
        </p>
        <div className="mt-3 flex gap-3">
          {(["cloud", "byok", "local"] as const).map((m) => (
            <ChromeButton key={m} onClick={() => void setMode(m)}>
              {m}
            </ChromeButton>
          ))}
        </div>
        {caps ? (
          <div className="mt-4 rounded-chrome bg-graphite-2 p-4 font-mono text-[12px] text-silver-dim">
            <p>
              GPU: {caps.gpu.name || "none"} ·{" "}
              {(caps.gpu.vram_total_mb / 1024).toFixed(1)}GB · {caps.gpu.backend}
            </p>
            <p>
              tier: <span className="text-fixer-hot">{caps.tier}</span> · ollama{" "}
              {caps.ollama.reachable ? "✓" : "✗"} · comfyui{" "}
              {caps.comfyui.reachable ? "✓" : "✗"} · whisper{" "}
              {caps.whisper_installed ? "✓" : "✗"}
            </p>
            <p className="mt-1 text-silver-dim/70">
              {String((caps.tier_detail as { note?: string }).note ?? "")}
            </p>
          </div>
        ) : null}
      </section>

      <section className="mb-10">
        <Wire tone="machine">bring your own keys</Wire>
        <p className="mt-1 text-label text-silver-dim">
          Keys are envelope-encrypted at rest, never logged, never shown again.
          The daily cap is enforced on our side regardless of the provider&apos;s.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-chrome bg-selenium px-4 py-2 text-label text-silver outline-none"
          >
            {["anthropic", "openai", "google", "fal", "deepgram"].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="api key"
            className="flex-1 rounded-chrome bg-selenium px-4 py-2 text-label text-silver outline-none placeholder:text-silver-dim/40"
          />
          <input
            type="number"
            value={cap}
            onChange={(e) => setCap(Number(e.target.value))}
            className="w-28 rounded-chrome bg-selenium px-4 py-2 font-mono text-label text-silver outline-none"
            title="daily cap in cents"
          />
          <SafelightButton onClick={() => void saveKey()} disabled={!key}>
            Store key
          </SafelightButton>
        </div>
        {byok.length ? (
          <ul className="mt-4 space-y-1 font-mono text-[12px] text-silver-dim">
            {byok.map((b) => (
              <li key={String(b.provider)}>
                {String(b.provider)} · cap ${(Number(b.daily_cap_cents) / 100).toFixed(2)}/day ·
                spent today ${(Number(b.spent_today_cents) / 100).toFixed(2)}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="mb-10">
        <Wire tone="machine">learning loops</Wire>
        <p className="mt-1 text-label text-silver-dim">
          Four loops learn from you: taste (swipes), voice (takes), format
          (picks), timing (posts). Each resets independently.
        </p>
        <div className="mt-3 flex gap-3">
          {["taste", "voice", "format", "timing"].map((loop) => (
            <ChromeButton key={loop} onClick={() => void resetLoop(loop)}>
              reset {loop}
            </ChromeButton>
          ))}
        </div>
      </section>

      <section>
        <ChromeButton
          onClick={() => {
            setToken(null);
            router.push("/");
          }}
        >
          Start a fresh session
        </ChromeButton>
        <p className="mt-2 text-label text-silver-dim">
          Clears this browser&apos;s session and walks you back in as a new guest.
        </p>
      </section>
    </div>
  );
}

interface ProtocolSourceRow {
  link_id: string;
  domain: string;
  name: string;
  url: string;
  kind: string;
}

function ProtocolEditor({ onNotice }: { onNotice: (s: string) => void }) {
  const [sources, setSources] = useState<ProtocolSourceRow[]>([]);
  const [url, setUrl] = useState("");

  const load = async () => {
    const res = await fetch("/api/wire/protocol", {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) {
      const data = (await res.json()) as { sources: ProtocolSourceRow[] };
      setSources(data.sources);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const add = async () => {
    if (!url.trim()) return;
    const res = await fetch("/api/wire/protocol/sources", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ url: url.trim() }),
    });
    if (res.ok) {
      setUrl("");
      onNotice("Source added. The next ingest cycle pulls from it.");
      void load();
    } else {
      onNotice("Couldn't add that source — check the URL.");
    }
  };

  const remove = async (linkId: string) => {
    await fetch(`/api/wire/protocol/sources/${linkId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    void load();
  };

  return (
    <section className="mb-10">
      <Wire tone="machine">protocol — your sources</Wire>
      <p className="mt-1 text-label text-silver-dim">
        The wire reads what you tell it to. Paste any site or RSS feed URL.
      </p>
      <div className="mt-3 flex gap-3">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void add()}
          placeholder="https://example.com/feed"
          className="flex-1 rounded-chrome bg-selenium px-4 py-2 text-label text-silver outline-none placeholder:text-silver-dim/40"
        />
        <SafelightButton onClick={() => void add()} disabled={!url.trim()}>
          Add source
        </SafelightButton>
      </div>
      {sources.length ? (
        <ul className="mt-4 space-y-1">
          {sources.map((s) => (
            <li
              key={s.link_id}
              className="flex items-center justify-between rounded-chrome bg-graphite-2 px-4 py-2"
            >
              <span className="font-mono text-[12px] text-silver-dim">
                {s.kind.toUpperCase()} · {s.domain || s.name}
              </span>
              <button onClick={() => void remove(s.link_id)}>
                <Wire tone="reject">remove</Wire>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-label text-silver-dim/60">
          No sources yet — the deck falls back to the shared pool.
        </p>
      )}
    </section>
  );
}
