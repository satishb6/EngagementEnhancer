"use client";

import { z } from "zod";

/** Every boundary is Zod-validated. The API base is proxied via /api/wire. */
const BASE = "/api/wire";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("wire_token");
}

export function setToken(token: string | null): void {
  if (token) window.localStorage.setItem("wire_token", token);
  else window.localStorage.removeItem("wire_token");
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  schema: z.ZodType<T>,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return schema.parse(await res.json());
}

/* ---------------------------------- schemas -------------------------------- */

export const TokenResponse = z.object({
  token: z.string(),
  user_id: z.string(),
  email: z.string(),
  display_name: z.string(),
  tier: z.string(),
});

export const BriefingSchema = z.object({
  id: z.string(),
  headline: z.string(),
  body: z.string(),
  word_count: z.number(),
  confidence: z.string(),
  contested: z.boolean(),
  source_links: z.array(
    z.object({ url: z.string(), domain: z.string(), title: z.string().optional() }),
  ),
  published_at: z.string().nullable(),
  cluster_id: z.string(),
});
export type Briefing = z.infer<typeof BriefingSchema>;

export const FeedItemSchema = z.object({
  feed_item_id: z.string(),
  position: z.number(),
  rank_score: z.number(),
  briefing: BriefingSchema,
});
export type FeedItem = z.infer<typeof FeedItemSchema>;

export const FeedResponse = z.object({
  items: z.array(FeedItemSchema),
  next_cursor: z.number(),
  total_today: z.number(),
});

export const SuggestionSchema = z.object({
  stance: z.string(),
  text: z.string(),
  source: z.string(),
});
export type Suggestion = z.infer<typeof SuggestionSchema>;

export const KeepSchema = z.object({
  feed_item_id: z.string(),
  briefing: BriefingSchema,
  take: z
    .object({ id: z.string(), text: z.string(), stance: z.string(), source: z.string() })
    .nullable(),
});
export type Keep = z.infer<typeof KeepSchema>;

export const ArtifactSchema = z.object({
  id: z.string(),
  content_type: z.string(),
  variant_index: z.number(),
  text_content: z.string(),
  storage_uri: z.string(),
  width: z.number().nullable(),
  height: z.number().nullable(),
  duration_ms: z.number().nullable(),
  meta: z.record(z.unknown()),
  created_at: z.string(),
});
export type Artifact = z.infer<typeof ArtifactSchema>;

export const SheetResponse = z.object({
  take_id: z.string(),
  artifacts: z.array(ArtifactSchema),
  jobs: z.array(
    z.object({
      id: z.string(),
      content_type: z.string(),
      state: z.string(),
      variant_index: z.number(),
      cost_estimate_cents: z.number(),
      cost_actual_cents: z.number().nullable(),
      error: z.record(z.unknown()).nullable(),
      storyboard: z.unknown().nullable(),
      awaiting_approval: z.boolean(),
    }),
  ),
  video_offers: z.array(
    z.object({
      content_type: z.string(),
      credits: z.number(),
      max_duration_s: z.number(),
      gated: z.boolean(),
    }),
  ),
});
export type Sheet = z.infer<typeof SheetResponse>;

export const GraphResponse = z.object({
  nodes: z.array(
    z.object({
      id: z.string(),
      kind: z.string(),
      headline: z.string(),
      position: z.array(z.number()).nullable(),
      region: z.string(),
      engagement: z.number(),
      has_take: z.boolean(),
      published_count: z.number(),
      last_touched: z.string(),
      created_at: z.string(),
      expired: z.boolean(),
    }),
  ),
  edges: z.array(
    z.object({ source: z.string(), target: z.string(), strength: z.number() }),
  ),
  regions: z.array(
    z.object({
      key: z.string(),
      count: z.number(),
      exposed: z.number(),
      position: z.array(z.number()),
    }),
  ),
});
export type Graph = z.infer<typeof GraphResponse>;

export const SummaryResponse = z.object({
  window_minutes: z.number(),
  stages: z.record(
    z.object({
      events: z.number(),
      failures: z.number(),
      error_rate: z.number(),
      p50_ms: z.number().nullable(),
      p95_ms: z.number().nullable(),
      cost_cents: z.number(),
    }),
  ),
  generated_at: z.string(),
});

export const MetersResponse = z.object({
  youtube_units: z.object({ used: z.number(), cap: z.number() }),
  credits: z.object({ burned_today: z.number(), balance: z.number() }),
  spend_today_cents: z.number(),
  local: z
    .object({ vram_used_mb: z.number(), vram_total_mb: z.number() })
    .optional(),
});

export const BalanceResponse = z.object({
  balance: z.number(),
  tier: z.string(),
  can_publish: z.boolean(),
  can_video: z.boolean(),
  variant_count: z.number(),
  selections_per_day: z.number(),
});

export const CapabilitiesResponse = z.object({
  gpu: z.object({
    name: z.string(),
    vram_total_mb: z.number(),
    vram_free_mb: z.number(),
    backend: z.string(),
  }),
  ollama: z.object({ reachable: z.boolean(), models: z.array(z.string()) }),
  comfyui: z.object({ reachable: z.boolean() }),
  whisper_installed: z.boolean(),
  tier: z.string(),
  tier_detail: z.record(z.unknown()),
});

export const VoiceMatchResponse = z.object({
  series: z.array(
    z.object({ week: z.string(), voice_match_pct: z.number(), takes: z.number() }),
  ),
  current: z.number().nullable(),
});

/* ----------------------------------- calls --------------------------------- */

export const api = {
  signup: (email: string, password: string, display_name = "") =>
    request("POST", "/auth/signup", TokenResponse, { email, password, display_name }),
  login: (email: string, password: string) =>
    request("POST", "/auth/login", TokenResponse, { email, password }),
  feed: (cursor = 0, limit = 20) =>
    request("GET", `/feed?cursor=${cursor}&limit=${limit}`, FeedResponse),
  swipe: (swipes: Array<{
    feed_item_id: string;
    direction: "left" | "right";
    dwell_ms: number;
    client_event_id: string;
  }>) =>
    request("POST", "/swipe", z.object({ accepted: z.number(), duplicates: z.number() }), {
      swipes,
    }),
  undoSwipe: () =>
    request("POST", "/swipe/undo", z.object({ undone_feed_item_id: z.string() })),
  keeps: () =>
    request("GET", "/session/keeps", z.object({ keeps: z.array(KeepSchema), count: z.number() })),
  suggest: (briefing_id: string) =>
    request("POST", "/take/suggest", z.object({
      briefing_id: z.string(),
      suggestions: z.array(SuggestionSchema),
    }), { briefing_id }),
  createTake: (body: {
    briefing_id: string;
    feed_item_id?: string;
    text: string;
    suggested_text?: string;
    stance?: string;
  }) =>
    request("POST", "/take", z.object({
      take_id: z.string(),
      source: z.string(),
      edit_distance_ratio: z.number(),
      generation_job_ids: z.array(z.string()),
    }), body),
  sheet: (takeId: string) => request("GET", `/takes/${takeId}/sheet`, SheetResponse),
  pick: (artifact_id: string, platform: string) =>
    request("POST", "/sheet/pick", z.object({ picked: z.string(), platform: z.string() }), {
      artifact_id,
      platform,
    }),
  requestVideo: (body: {
    take_id: string;
    long_form: boolean;
    duration_s: number;
    confirm_credits?: number;
  }) =>
    request("POST", "/generate/video", z.record(z.unknown()), body),
  graph: () => request("GET", "/graph", GraphResponse),
  graphNode: (id: string) => request("GET", `/graph/node/${id}`, z.record(z.unknown())),
  summary: (windowMinutes = 60) =>
    request("GET", `/events/summary?window_minutes=${windowMinutes}`, SummaryResponse),
  recentEvents: (stage: string) =>
    request("GET", `/events/recent?stage=${stage}`, z.array(z.record(z.unknown()))),
  trace: (traceId: string) =>
    request("GET", `/events/trace/${traceId}`, z.record(z.unknown())),
  meters: () => request("GET", "/system/meters", MetersResponse),
  balance: () => request("GET", "/billing/balance", BalanceResponse),
  capabilities: () => request("GET", "/system/capabilities", CapabilitiesResponse),
  voiceMatch: () => request("GET", "/system/learning/voice-match", VoiceMatchResponse),
  resetLoop: (loop: string) =>
    request("POST", `/system/learning/reset/${loop}`, z.object({ reset: z.string() })),
  accounts: () =>
    request("GET", "/publish/accounts", z.array(z.record(z.unknown()))),
  publishQueue: () =>
    request("GET", "/publish/queue", z.array(z.record(z.unknown()))),
  schedulePost: (body: { artifact_id: string; account_id: string; scheduled_for?: string }) =>
    request("POST", "/publish", z.record(z.unknown()), body),
  clipboard: (artifactId: string, platform: string) =>
    request("GET", `/publish/clipboard/${artifactId}?platform=${platform}`, z.object({
      platform: z.string(),
      text: z.string(),
      media_uri: z.string(),
      note: z.string(),
    })),
  slots: (platform: string) =>
    request("GET", `/publish/slots?platform=${platform}`, z.object({
      platform: z.string(),
      weekday: z.number(),
      hours: z.array(z.number()),
    })),
  jobs: (takeId?: string) =>
    request("GET", `/jobs${takeId ? `?take_id=${takeId}` : ""}`, z.array(z.record(z.unknown()))),
};

export function eventStreamUrl(stage?: string): string {
  const params = new URLSearchParams();
  if (stage) params.set("stage", stage);
  return `${BASE}/events/stream?${params.toString()}`;
}
