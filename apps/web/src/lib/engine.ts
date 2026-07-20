"use client";

/**
 * The engine config — the EIP pattern: keys live in YOUR browser
 * (localStorage), travel per-request as headers, and are never stored on
 * the server. Demo mode needs no key at all.
 */

export interface ProviderSpec {
  id: string;
  name: string;
  free: boolean;
  keyUrl: string;
  keyHint: string;
  defaultModel: string;
  note: string;
}

export const PROVIDERS: ProviderSpec[] = [
  {
    id: "demo", name: "Demo (no key)", free: true, keyUrl: "", keyHint: "",
    defaultModel: "deterministic",
    note: "Zero setup. Real mechanics, template writing. Start here.",
  },
  {
    id: "groq", name: "Groq", free: true,
    keyUrl: "https://console.groq.com/keys", keyHint: "gsk_...",
    defaultModel: "llama-3.3-70b-versatile",
    note: "FREE tier, very fast. The recommended first real key.",
  },
  {
    id: "google", name: "Google Gemini", free: true,
    keyUrl: "https://aistudio.google.com/apikey", keyHint: "AIza...",
    defaultModel: "gemini-2.0-flash",
    note: "FREE tier for text AND embeddings (smarter dedup + ranking).",
  },
  {
    id: "openrouter", name: "OpenRouter", free: true,
    keyUrl: "https://openrouter.ai/keys", keyHint: "sk-or-...",
    defaultModel: "meta-llama/llama-3.3-70b-instruct:free",
    note: "One key, many models — several are :free.",
  },
  {
    id: "ollama", name: "Ollama (local GPU)", free: true, keyUrl: "", keyHint: "",
    defaultModel: "llama3.1:8b",
    note: "Fully private, runs on your own machine. Needs Ollama running.",
  },
  {
    id: "openai", name: "OpenAI", free: false,
    keyUrl: "https://platform.openai.com/api-keys", keyHint: "sk-...",
    defaultModel: "gpt-4o-mini", note: "Paid. Also unlocks OpenAI embeddings.",
  },
  {
    id: "anthropic", name: "Anthropic Claude", free: false,
    keyUrl: "https://console.anthropic.com", keyHint: "sk-ant-...",
    defaultModel: "claude-haiku-4-5-20251001", note: "Paid. Excellent writing quality.",
  },
  {
    id: "deepseek", name: "DeepSeek", free: false,
    keyUrl: "https://platform.deepseek.com", keyHint: "sk-...",
    defaultModel: "deepseek-chat", note: "Very cheap paid tier.",
  },
  {
    id: "mistral", name: "Mistral", free: false,
    keyUrl: "https://console.mistral.ai", keyHint: "...",
    defaultModel: "mistral-small-latest", note: "Free experiment tier available.",
  },
  {
    id: "fal", name: "fal.ai (images/video)", free: false,
    keyUrl: "https://fal.ai/dashboard/keys", keyHint: "key-id:secret",
    defaultModel: "flux", note: "Optional: real images + video instead of placeholders.",
  },
];

export interface EngineConfig {
  provider: string; // "" = auto (free-first), "demo", or a provider id
  model: string;
  keys: Record<string, string>;
}

const STORAGE_KEY = "wire_engine";

export function loadEngine(): EngineConfig {
  if (typeof window === "undefined") return { provider: "", model: "", keys: {} };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return { provider: "", model: "", keys: {}, ...JSON.parse(raw) };
  } catch {
    /* corrupted storage — reset */
  }
  return { provider: "", model: "", keys: {} };
}

export function saveEngine(config: EngineConfig): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

/** Headers attached to every API request. Keys never go anywhere else. */
export function engineHeaders(): Record<string, string> {
  const engine = loadEngine();
  const headers: Record<string, string> = {};
  const keys = Object.fromEntries(
    Object.entries(engine.keys).filter(([, v]) => v && v.trim()),
  );
  if (Object.keys(keys).length) headers["X-Wire-Keys"] = JSON.stringify(keys);
  if (engine.provider) headers["X-Wire-Provider"] = engine.provider;
  if (engine.model) headers["X-Wire-Model"] = engine.model;
  return headers;
}
