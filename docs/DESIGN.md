# WIRE — Design Direction

### The idea: a darkroom, not a dashboard

News arrives over **the wire** as raw signal. It gets **developed** into a print you can read. You mark up a **contact sheet** to choose which frames survive. Then you make the **final print** and put it on the wall.

That's the whole product, and it's also the whole visual system. Every screen is one of those four rooms. The interface is dark because darkrooms are dark — and the things you're actually reading are luminous prints suspended in that dark.

This is deliberately *not*: a cyberpunk neon grid, a cream-and-terracotta editorial site, or a broadsheet pastiche with hairline rules. Those are the three places this kind of brief usually lands. We're going somewhere else.

### Palette — six values, no more

| Token | Hex | Role |
|---|---|---|
| `graphite` | `#12161B` | The room. App ground, edge to edge. |
| `selenium` | `#1E262F` | Raised machine surfaces — nav, sheets, controls. |
| `silver` | `#DAD5C9` | **The print.** Every piece of readable content sits on this. Warm, slightly foxed, never pure white. |
| `safelight` | `#FF8A3D` | **You.** Every human action: swipe right, your opinion, publish, select. |
| `fixer` | `#6D64A3` | **The machine.** Extraction, generation, AI states, graph structure. |
| `fixer-hot` | `#9A8EE0` | Active machine state only — a job actually running, a node actually selected. Used sparingly enough that it always means *now*. |
| `spike` | `#C4453C` | Reject. Left-swipe, discard, destructive. Used sparingly — it should feel like a decision. |

The safelight/fixer split is the most important rule in this document. **Colour encodes agency.** A user should be able to glance at any screen and know instantly which parts of it they made and which parts the machine made. Never use them decoratively. Never mix them in a gradient.

Neutrals derive from `graphite` and `silver` only. No grey ramp from a framework default.

### Type — three faces, three jobs

**Redaction** — display. Briefing headlines, screen titles, the big moments.
The halftone grade carries meaning:
- `Redaction 100` (finest) — human-authored text. Your opinion, your edits.
- `Redaction 35` — briefings. Journalism, processed but faithful.
- `Redaction 10` (coarsest) — AI-generated copy, before you've touched it.

When a user edits AI text, the grade animates from 10 → 100 as they type. That single detail does more to communicate "this is yours now" than any label could.

**Instrument Sans** — interface. Buttons, labels, body, navigation. Set tight: `-0.011em` tracking at UI sizes.

**Martian Mono** — the wire. Timestamps, source counts, credit balances, cluster IDs, anything the machine measured. Always uppercase, always `0.08em` tracked, always small. It's instrument labelling, not text.

**Scale** (mobile / web):
```
display-xl   40 / 56   Redaction 35, -0.02em
display      30 / 40   Redaction 35
briefing     22 / 28   Redaction 35, 1.35 leading
body         16 / 17   Instrument Sans, 1.6 leading
label        13 / 14   Instrument Sans 500
wire         10 / 11   Martian Mono, 0.08em, uppercase
```

### Material

Prints are **objects**. They have edges, they cast shadows, they're not flat rectangles with `border-radius: 12px`.

- Print surfaces: `radius: 3px` (paper is cut, not rounded), a 1px inner highlight at 6% white on the top edge, and a real shadow — `0 24px 48px -12px rgba(0,0,0,0.7)`.
- Machine chrome: `radius: 10px`, no shadow, separated by tone not by border.
- Grain: a 2–3% opacity noise overlay across the entire app, always. It removes the flat-digital feeling in one line and unifies the 3D and 2D layers so they don't look bolted together.
- No glassmorphism. No frosted blur panels. That's a different decade's darkroom.

### Motion

Springs, not easings. Everything interruptible. Nothing over 400ms except the deliberate set-pieces.

```
snap     stiffness 400, damping 30    taps, toggles
settle   stiffness 220, damping 26    cards landing, sheets
develop  stiffness 90,  damping 20    the print-development reveal
```

**The develop transition** is the app's signature motion. When a briefing appears, it doesn't fade in — it *develops*: starts near-black with heavy grain, and over ~700ms the grain resolves and the silver surface emerges, exactly like watching a print come up in a tray. Used only for briefings and finished content. Never for UI chrome.

Respect `prefers-reduced-motion`: all springs collapse to 120ms opacity fades, the develop transition becomes a straight cut, 3D falls back to static composition.

### The three signatures

**1. The Contact Sheet** — the version picker, rendered as an actual photographic contact sheet. A grid of numbered frames on a single silver print. Frame numbers in Martian Mono down the left edge. Selecting a frame draws a **grease-pencil circle** around it, in safelight orange, stroked on with a hand-drawn wobble over 300ms — the gesture a photo editor has made for a hundred years.

**2. The Wire Room** — every backend process, visible and live. Not a log viewer: a signal-flow diagram where data physically moves between stages, every node inspectable, every cost accruing in real time.

**3. The Lattice** — the 3D knowledge graph.

Everything not on this list stays quiet. The restraint is what makes these three land.

---

### THE WIRE ROOM — transparent processing

*Mandatory build. This is not a debugging tool — it's a primary screen.*

The premise: nothing the machine does is hidden. A user in BYOK or local mode is spending their own money and their own GPU; a user on the paid tier is spending credits. In all three cases, opacity is a trust failure.

**What it shows.** A horizontal signal-flow diagram of the live pipeline:

```
SOURCES ──▶ FETCH ──▶ EMBED ──▶ CLUSTER ──▶ BRIEF ──▶ RANK ──▶ [you] ──▶ GENERATE ──▶ PUBLISH
```

Each stage is a node in `selenium` with a Martian Mono label and a live counter. Work in flight travels between nodes as small particles in `fixer-hot` — one particle per item, moving at a speed proportional to actual throughput. When a stage is idle the particles stop. The screen is genuinely dead when nothing is happening, and that honesty is the point.

**Inspection.** Tapping any stage opens a Print panel showing:
- The last 50 events through that stage, newest first
- For model calls: provider, model ID, token counts, latency, cost in cents, and the actual prompt and response
- For ingestion: source, HTTP status, items fetched vs. new, quota units consumed
- For generation: the full job record including estimate vs. actual

**Quota and budget meters** run along the top: YouTube API units consumed against the daily 10,000 ceiling, X API spend, credits burned today, and in local mode, GPU VRAM and queue depth.

**The architectural consequence:** this cannot be retrofitted. Every backend operation must emit a structured trace event from Phase 1. Build the event spine before the pipeline, not after.

---

### THE LATTICE — the 3D knowledge graph

*Mandatory build. Named for the silver halide crystal lattice in film emulsion — the structure on which an image develops when light hits it. Your interests are the lattice; the news is the light.*

**Structure.**

| Element | Meaning |
|---|---|
| Node (large) | A topic region — a cluster of semantically related news clusters |
| Node (small) | An individual briefing |
| Node (satellite) | A source domain |
| Node (bright, `safelight`) | A briefing you wrote a take on — these are *yours* |
| Edge | Real cosine similarity above threshold. Thickness = strength. |
| Node size | Engagement volume |
| Node luminance | Recency — old nodes darken but never vanish |

**Position is real.** Run UMAP on the briefing embeddings down to 3 dimensions, cache the projection, and use it to seed a force-directed layout. Regions of the graph correspond to actual regions of semantic space.

**The exposure metaphor.** Unengaged nodes sit dim and cool in `fixer` — unexposed crystals. Nodes you've taken a position on are exposed: brighter, warmer, drawn in `safelight`, with a faint bloom. Watching your lattice expose over weeks is the retention mechanic.

**Interaction.**
- Orbit, pan, zoom. Momentum on release.
- Hover a node: it and its neighbours lift out; everything else drops to 15% opacity
- Tap a node: a Print panel slides in with the briefing, your take if you wrote one, what you published, and how it performed
- Tap a region label: boost, mute, or add to a protocol — the graph is how you edit your own feed
- **Timeline scrub** along the bottom: drag back through time and watch the lattice grow from nothing.
- Search: type, and matching nodes flare while the rest recede

**Performance.** Instanced meshes for nodes, a single merged `BufferGeometry` for edges, LOD by camera distance, frustum culling. Target 60fps at 2,000 nodes on desktop and 500 on mobile. Above the node budget, collapse the least-engaged nodes into region aggregates rather than dropping frames.

**Reduced motion / low power:** falls back to a static 2D projection with the same colour semantics and the same tap targets. Never a blank state.

### Voice

Interface copy is plain, active, and specific. Buttons say what happens: "Post it," not "Submit." Errors state what broke and the next move, without apologising. Empty states are invitations, not decorations.

The machine never speaks in first person. It doesn't say "I've generated 3 versions." It says "3 versions ready."
