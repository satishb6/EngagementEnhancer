import AsyncStorage from "@react-native-async-storage/async-storage";

const BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem("wire_token");
}

export async function setToken(token: string | null): Promise<void> {
  if (token) await AsyncStorage.setItem("wire_token", token);
  else await AsyncStorage.removeItem("wire_token");
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = ((await res.json().catch(() => ({}))) as { detail?: string }).detail;
    throw new Error(detail ?? `${res.status}`);
  }
  return (await res.json()) as T;
}

export interface Briefing {
  id: string;
  headline: string;
  body: string;
  source_links: Array<{ url: string; domain: string }>;
  published_at: string | null;
  cluster_id: string;
  confidence: string;
}

export interface FeedItem {
  feed_item_id: string;
  position: number;
  briefing: Briefing;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ token: string }>("POST", "/auth/login", { email, password }),
  signup: (email: string, password: string) =>
    request<{ token: string }>("POST", "/auth/signup", { email, password }),
  feed: () =>
    request<{ items: FeedItem[]; total_today: number }>("GET", "/feed?limit=50"),
  swipe: (swipes: Array<{
    feed_item_id: string;
    direction: "left" | "right";
    dwell_ms: number;
    client_event_id: string;
  }>) => request<{ accepted: number }>("POST", "/swipe", { swipes }),
  undo: () => request<{ undone_feed_item_id: string }>("POST", "/swipe/undo"),
  keeps: () =>
    request<{ keeps: Array<{ feed_item_id: string; briefing: Briefing; take: { id: string; text: string } | null }> }>(
      "GET",
      "/session/keeps",
    ),
  suggest: (briefing_id: string) =>
    request<{ suggestions: Array<{ stance: string; text: string }> }>(
      "POST",
      "/take/suggest",
      { briefing_id },
    ),
  createTake: (body: {
    briefing_id: string;
    feed_item_id?: string;
    text: string;
    suggested_text?: string;
    stance?: string;
  }) => request<{ take_id: string }>("POST", "/take", body),
};
