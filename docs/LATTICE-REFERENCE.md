# Lattice reference — extracted visual language

**Source situation:** the playbook (3.6c Step 1) calls for reading the
neural-map section of the reference portfolio repo. That repo is **not on
this machine** (searched all of `D:\` and the user profile — no three.js
projects exist here). This document instead extracts the observable
parameters from the supplied screenshot of the reference ("KNOWLEDGE GRAPH /
neural map", the SRUJAN graph). If the repo surfaces later, tighten this
against the actual code and re-tune.

## What produces the feel (from the screenshot)

| Element | Observed treatment | Carried into WIRE |
|---|---|---|
| Ground | Near-black, slightly blue (#050a0e-ish), edge-to-edge; faint grid texture barely visible | `#0E1116` (graphite-family), grain overlay supplies the texture |
| Nodes | Glossy, plastic-like spheres; strong specular highlight upper-left; saturated hues; soft bloom halo on bright nodes | MeshStandard, roughness ~0.22, metalness ~0.05, emissive tint per state, key light upper-left |
| Node hierarchy | Large hub spheres per cluster, small satellites around them; centre node brightest/white | region hubs > briefings > sources; exposed nodes brightest |
| Colour | Category-coded saturated hues (blue/orange/purple/green/magenta) | **Overridden by WIRE's agency rule**: fixer (unexposed) / safelight (exposed) / fixer-hot (active). The reference's *luminance relationships* survive: hubs brighter than satellites, active brighter than idle |
| Edges | Thin (~1px), neutral grey, low opacity, straight lines; denser inside clusters, sparse cross-cluster | merged BufferGeometry lines, vertex-coloured, opacity 0.4–0.6 by strength |
| Labels | Uppercase mono, tracked, small, tinted to the cluster hue, floating at cluster centroids, always camera-facing | Martian Mono billboards at region centroids, safelight when exposed |
| Camera | Perspective with mild tilt; drag-to-orbit with momentum; comfortable dolly range | OrbitControls, damping 0.06, min 12 / max 120 |
| Interaction | Hover reveals names; click opens details; a query "lights up" matching nodes while the rest recede | hover lift + neighbourhood isolate at 15%; search flare; tap → Print panel |
| Legend/HUD | Small mono chips bottom-left with counts; instruction card top-right | counts top-left, search top-right, timeline scrub bottom |

## The luminance ladder (the part that must read identically)

1. Selected / matching-search node — brightest, bloomed
2. Exposed node (has a take) — bright, warm
3. Region hub — mid-bright, cool
4. Unexposed briefing — dim, cool
5. Aged node — darkened toward ground, never invisible
6. Edges — always below every node's brightness

## Divergences, stated honestly

- The reference colour-codes by *category*; WIRE colour-codes by *agency*
  (design-doc rule 1 — colour encodes who made it, not what it's about).
- The reference appears to use postprocessing bloom; WIRE approximates with
  emissive materials to keep the mobile/low-power path cheap. If a real
  bloom pass is wanted later: UnrealBloomPass, threshold ~0.6, strength
  ~0.7, radius ~0.4 would match the screenshot's halo width.
- Reference cluster layout looks force-directed from random seed; WIRE's
  positions are semantic (UMAP/PCA of real embeddings) — a deliberate
  upgrade, kept.
