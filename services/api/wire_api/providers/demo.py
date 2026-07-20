"""Zero-key demo providers — the deterministic cores.

With no key at all, WIRE still works end to end: briefings are extractive
(real sentences from the real articles, word-capped), suggestions are three
genuinely opposed stances, composition is a clean template over the user's
own words, and embeddings are deterministic hashed n-grams (stable, so
dedup/ranking behave consistently — just not semantic). Every output is
honestly labelled provider "demo". A single free Groq or Gemini key upgrades
the narration; the mechanics never depended on it.
"""

import hashlib
import json
import math
import re
import time

from wire_api.models.base import EMBED_DIM
from wire_api.providers.base import (
    EmbeddingResult,
    ImageResult,
    Message,
    ResultMeta,
    TextResult,
)

_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _meta(model: str, t0: float) -> ResultMeta:
    return ResultMeta(0.0, (time.perf_counter() - t0) * 1000, "demo", model)


def _extractive_briefing(payload: dict) -> str:  # type: ignore[type-arg]
    reports = payload.get("reports", [])
    titles = [str(r.get("title", "")) for r in reports if r.get("title")]
    headline_words = (titles[0] if titles else "News event reported").split()[:8]
    headline = " ".join(headline_words).rstrip(".:,?")
    sentences: list[str] = []
    for r in reports:
        for s in _SENT_RE.split(str(r.get("body", ""))):
            s = s.strip()
            if 30 <= len(s) <= 220:
                sentences.append(s)
    body_words: list[str] = []
    for s in sentences:
        if len(body_words) + len(s.split()) > 58:
            break
        body_words.extend(s.split())
    if len(body_words) < 35:
        filler = ("Reports describe the event with attribution to the listed sources. "
                  "Details continue to emerge and coverage differs on scope.").split()
        body_words.extend(filler[: 40 - len(body_words)])
    return json.dumps({
        "headline": headline or "News event reported",
        "body": " ".join(body_words[:58]),
        "confidence": "medium" if len(reports) > 1 else "low",
        "claims": [],
    })


_STANCES = [
    ("SKEPTICAL", "I'd hold the applause — the incentives behind this matter more "
                  "than the announcement itself."),
    ("OPTIMISTIC", "Quietly, this is a bigger deal than the coverage suggests; I "
                   "think we look back at it as a turning point."),
    ("CONTRARIAN", "Everyone is reading this the same way, which usually means the "
                   "consensus is about to be wrong."),
]


class DemoTextProvider:
    """Routes by intent: Editor gets extractive JSON, Provocateur gets three
    stances, Composer gets a template over the user's take."""

    provider_id = "demo"

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        t0 = time.perf_counter()
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        try:
            payload = json.loads(user)
        except json.JSONDecodeError:
            payload = {}

        if "You are the Editor" in system:
            text = _extractive_briefing(payload)
        elif "You are the Provocateur" in system:
            text = json.dumps([{"stance": s, "text": t} for s, t in _STANCES])
        elif "You are the Composer" in system:
            take = str(payload.get("take", {}).get("text", "")).strip()
            briefing = payload.get("briefing", {})
            headline = str(briefing.get("headline", ""))
            links = briefing.get("source_links", [])
            link = str(links[0].get("url", "")) if links else ""
            variant = int(payload.get("variant_index", 0))
            if variant == 0:
                text = f"{take}\n\nContext: {headline}." + (f"\n{link}" if link else "")
            elif variant == 1:
                text = f"{headline}.\n\n{take}" + (f"\n{link}" if link else "")
            else:
                text = f"Worth sitting with this one: {headline}.\n\n{take}"
        elif "You are the Stenographer" in system or "You are the Director" in system:
            text = "{}"
        else:
            text = ("Demo mode: add a free Groq or Google Gemini key in Studio → "
                    "Engine for real AI writing. The mechanics you're using are real.")
        return TextResult(text=text, input_tokens=0, output_tokens=len(text.split()),
                          meta=_meta("deterministic", t0))

    async def healthy(self) -> bool:
        return True


class HashEmbeddingProvider:
    """Deterministic character-n-gram hashing → unit vector. Not semantic,
    but stable: identical text always lands in the same place, near-identical
    text lands nearby — enough for dedup and non-embarrassing ranking."""

    provider_id = "hash-embed"

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        t0 = time.perf_counter()
        vectors = []
        for text in texts:
            vec = [0.0] * EMBED_DIM
            clean = re.sub(r"\s+", " ", text.lower())[:4000]
            for n in (3, 5):
                for i in range(len(clean) - n + 1):
                    gram = clean[i:i + n]
                    h = int.from_bytes(
                        hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big"
                    )
                    vec[h % EMBED_DIM] += 1.0 if (h >> 63) else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return EmbeddingResult(vectors=vectors, input_tokens=0,
                               meta=_meta("blake2b-ngram", t0))

    async def healthy(self) -> bool:
        return True


class DemoImageProvider:
    """A labelled SVG placeholder so contact sheets are never broken frames."""

    provider_id = "demo-image"

    async def generate(
        self, prompt: str, *, size: str = "1024x1024", n: int = 1, seed: int | None = None
    ) -> list[ImageResult]:
        t0 = time.perf_counter()
        w, h = (int(x) for x in size.split("x"))
        words = " ".join(prompt.split()[:10])
        seed_val = seed if seed is not None else abs(hash(prompt)) % 999
        hue = (seed_val * 47) % 360
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
            f"<rect width='100%' height='100%' fill='hsl({hue},35%,18%)'/>"
            f"<circle cx='{w // 2}' cy='{h // 2}' r='{h // 4}' fill='hsl({hue},55%,32%)'/>"
            f"<text x='24' y='{h - 48}' fill='#DAD5C9' font-family='monospace' "
            f"font-size='20'>DEMO FRAME — add a fal.ai key for real images</text>"
            f"<text x='24' y='{h - 24}' fill='#9A8EE0' font-family='monospace' "
            f"font-size='14'>{words}</text></svg>"
        )
        import base64

        url = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        return [ImageResult(url=url, width=w, height=h, seed=seed_val,
                            meta=_meta("svg-placeholder", t0))]

    async def healthy(self) -> bool:
        return True
