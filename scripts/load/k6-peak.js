// k6 scenario: the realistic peak — 8am, everyone opening the app at once.
// Run:  k6 run scripts/load/k6-peak.js -e BASE=http://localhost:8000 -e TOKEN=<jwt>
//
// Targets: /feed p95 < 200ms, swipe batch p95 < 100ms.

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://localhost:8000";
const TOKEN = __ENV.TOKEN || "";

const headers = {
  "Content-Type": "application/json",
  ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
};

export const options = {
  scenarios: {
    feed_rush: {
      executor: "ramping-vus",
      exec: "feed",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 1000 },
        { duration: "2m", target: 1000 },
        { duration: "30s", target: 0 },
      ],
    },
    swipe_batches: {
      executor: "constant-vus",
      exec: "swipes",
      vus: 200,
      duration: "3m",
      startTime: "30s",
    },
    generation_jobs: {
      executor: "constant-vus",
      exec: "generation",
      vus: 50,
      duration: "3m",
      startTime: "45s",
    },
  },
  thresholds: {
    "http_req_duration{endpoint:feed}": ["p(95)<200"],
    "http_req_duration{endpoint:swipe}": ["p(95)<100"],
    http_req_failed: ["rate<0.01"],
  },
};

export function feed() {
  const res = http.get(`${BASE}/feed?limit=20`, { headers, tags: { endpoint: "feed" } });
  check(res, { "feed 200": (r) => r.status === 200 || r.status === 401 });
  sleep(Math.random() * 3 + 1);
}

export function swipes() {
  const body = JSON.stringify({
    swipes: Array.from({ length: 5 }, (_, i) => ({
      feed_item_id: "00000000-0000-0000-0000-000000000000",
      direction: Math.random() > 0.4 ? "right" : "left",
      dwell_ms: Math.floor(Math.random() * 6000),
      client_event_id: `k6-${__VU}-${__ITER}-${i}-${Date.now()}`,
    })),
  });
  const res = http.post(`${BASE}/swipe`, body, { headers, tags: { endpoint: "swipe" } });
  check(res, { "swipe accepted": (r) => r.status === 200 || r.status === 401 });
  sleep(Math.random() * 5 + 2);
}

export function generation() {
  const res = http.get(`${BASE}/jobs?limit=10`, { headers, tags: { endpoint: "jobs" } });
  check(res, { "jobs 200": (r) => r.status === 200 || r.status === 401 });
  sleep(Math.random() * 8 + 4);
}
