"use client";

/**
 * Prints — the library and the publish flow. The publish action is the
 * largest safelight element in the app. Free tier gets "Copy for [platform]"
 * plus one honest line about what upgrading changes. No nag, no modal.
 */

import { useCallback, useEffect, useState } from "react";
import { z } from "zod";
import { api, ArtifactSchema, type Artifact } from "@/lib/api";
import {
  ChromeButton,
  Print,
  RedactionText,
  SafelightButton,
  Wire,
} from "@/components/ui/primitives";

interface AccountRow {
  id: string;
  platform: string;
  handle: string;
}

const PLATFORMS = ["x", "linkedin", "threads", "instagram"] as const;

async function fetchArtifacts(): Promise<Artifact[]> {
  const res = await fetch("/api/wire/artifacts", {
    headers: { Authorization: `Bearer ${localStorage.getItem("wire_token") ?? ""}` },
  });
  if (!res.ok) return [];
  return z.array(ArtifactSchema).parse(await res.json());
}

export default function PrintsPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [queue, setQueue] = useState<Array<Record<string, unknown>>>([]);
  const [canPublish, setCanPublish] = useState(false);
  const [slots, setSlots] = useState<number[]>([]);
  const [platform, setPlatform] = useState<string>("x");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const [rows, balance] = await Promise.all([fetchArtifacts(), api.balance()]);
        setArtifacts(rows);
        setCanPublish(balance.can_publish);
        if (balance.can_publish) {
          const [accountRows, queueRows] = await Promise.all([
            api.accounts(),
            api.publishQueue(),
          ]);
          setAccounts(accountRows as unknown as AccountRow[]);
          setQueue(queueRows);
        }
      } catch {
        /* the shell redirects unauthenticated users */
      }
    })();
  }, []);

  useEffect(() => {
    void api
      .slots(platform)
      .then((s) => setSlots(s.hours))
      .catch(() => setSlots([]));
  }, [platform]);

  const copyIt = useCallback(
    async (artifact: Artifact) => {
      try {
        const clip = await api.clipboard(artifact.id, platform);
        await navigator.clipboard.writeText(clip.text || artifact.text_content);
        setNotice(clip.note);
      } catch {
        await navigator.clipboard.writeText(artifact.text_content);
        setNotice("Copied the text.");
      }
    },
    [platform],
  );

  const postIt = useCallback(
    async (artifact: Artifact) => {
      const account = accounts.find((a) => a.platform === platform);
      if (!account) {
        setNotice(`Connect a ${platform} account first.`);
        return;
      }
      try {
        await api.schedulePost({ artifact_id: artifact.id, account_id: account.id });
        setNotice("Scheduled into the next good slot.");
        setQueue(await api.publishQueue());
      } catch (e) {
        setNotice(e instanceof Error ? e.message : "Posting failed.");
      }
    },
    [accounts, platform],
  );

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Wire tone="dim">the wall</Wire>
      <h1 className="mb-8 mt-1 text-display">
        <RedactionText grade={35}>Prints</RedactionText>
      </h1>

      {/* account chips: connected = full colour, available = outline */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {PLATFORMS.map((p) => {
          const connected = accounts.find((a) => a.platform === p);
          return (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`rounded-full px-4 py-1.5 text-label ${
                connected
                  ? "bg-safelight font-semibold text-ink"
                  : "border border-rule-strong text-silver-dim"
              } ${platform === p ? "outline outline-1 outline-fixer-hot" : ""}`}
            >
              {p}
              {connected ? ` · ${connected.handle || "linked"}` : ""}
            </button>
          );
        })}
        {!canPublish ? (
          <Wire tone="dim">free tier copies to clipboard · pro posts for you</Wire>
        ) : null}
      </div>

      {canPublish && slots.length ? (
        <div className="mb-6 flex items-center gap-3">
          <Wire tone="machine">good hours for {platform} today</Wire>
          {slots.map((h) => (
            <span
              key={h}
              className="rounded-chrome bg-selenium px-3 py-1 font-mono text-[12px] text-fixer-hot"
            >
              {String(h).padStart(2, "0")}:00
            </span>
          ))}
        </div>
      ) : null}

      {notice ? <p className="mb-6 text-label text-safelight">{notice}</p> : null}

      <div className="grid gap-6 sm:grid-cols-2">
        {artifacts.length === 0 ? (
          <p className="col-span-2 py-16 text-center text-body text-silver-dim">
            No finished prints yet. Takes in the Darkroom become prints here.
          </p>
        ) : null}
        {artifacts.map((artifact) => (
          <Print
            key={artifact.id}
            className="flex flex-col p-6"
            caption={`${artifact.content_type.toUpperCase()} · V${artifact.variant_index + 1} · ${new Date(artifact.created_at).toLocaleDateString()}`}
          >
            {artifact.content_type === "text" ? (
              <p className="flex-1 text-[14px] leading-relaxed text-ink-soft">
                {artifact.text_content}
              </p>
            ) : artifact.storage_uri ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={artifact.storage_uri}
                alt="print"
                className="max-h-64 w-full flex-1 rounded-print object-cover"
              />
            ) : (
              <Wire tone="machine">{artifact.content_type}</Wire>
            )}
            <div className="mt-4 flex justify-end">
              {canPublish ? (
                <SafelightButton big onClick={() => void postIt(artifact)}>
                  Post it
                </SafelightButton>
              ) : (
                <ChromeButton onClick={() => void copyIt(artifact)}>
                  Copy for {platform}
                </ChromeButton>
              )}
            </div>
          </Print>
        ))}
      </div>

      {queue.length ? (
        <div className="mt-12">
          <Wire tone="dim">scheduled &amp; posted</Wire>
          <ul className="mt-3 divide-y divide-rule">
            {queue.map((q) => (
              <li
                key={String(q.id)}
                className="flex items-baseline gap-4 py-2 font-mono text-[12px]"
              >
                <span
                  className={
                    q.status === "posted"
                      ? "text-safelight"
                      : q.status === "dead_letter"
                        ? "text-spike"
                        : "text-fixer-hot"
                  }
                >
                  {String(q.status)}
                </span>
                <span className="text-silver-dim">
                  {String(q.scheduled_for ?? q.posted_at ?? "")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
