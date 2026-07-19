# Design critique — an honest read before building

The brief asks: which parts of DESIGN.md would I have produced by default anyway,
without the document? Those are the weak points, because they're the places the
system is generic rather than earned.

## What I would have done by default anyway

1. **Dark ground + one warm accent + one cool accent.** Every AI-adjacent product
   ships this. `graphite`/`safelight`/`fixer` as raw hex values are not distinctive;
   what rescues them is the *agency rule* (orange = you, violet = machine), which I
   would NOT have produced by default. The palette is generic; the semantics are not.
   Conclusion: the discipline lives or dies on enforcement. The tokens file exports
   an `agency` alias so call-sites declare intent, and visual QA audits against it.

2. **A mono face for "data-ish" labels.** Martian Mono for timestamps is a default
   move. The non-default part is the constraint — *always* uppercase, *always*
   0.08em, *always* small, never for prose. Kept because the constraint is the point.

3. **Noise/grain overlay.** Grain overlays are a well-worn trick. It earns its place
   here only because the darkroom metaphor gives it a reason and the develop
   transition uses grain as its mechanism, not just its garnish. If the develop
   transition didn't exist, I'd cut the grain.

4. **Spring motion.** Framer-Motion-flavoured springs are the industry default.
   The named, semantic trio (snap/settle/develop) with hard rules about which one a
   surface may use is the differentiated part.

## What I would never have produced by default

- The **Redaction grade as provenance** (10 = machine, 100 = yours, animating as
  you edit). This is the single best idea in the document.
- The **print as object** rule (3px cut corners, top-edge highlight, real shadow)
  against machine chrome separated by tone. It gives the app two physically
  different materials, which is rare.
- The Wire Room's honesty rule: **no idle animation**. Dead screen = dead pipeline.
- The Contact Sheet's grease-pencil selection.

## The one concrete change I propose

**Make source provenance a first-class visual element of the print itself.**
As specified, briefings are typographically beautiful but their *sourcing* is
chips at the bottom — which is what any news app does. For a product whose whole
ethic is "neutral substrate + your opinion," the print should carry its evidence
the way a real wire photo carried its caption strip: a fixed **caption rail**
along the bottom edge of every Print surface, set in Martian Mono, listing
domain · timestamp · cluster size ("4 SOURCES · 41M AGO · CLUSTER 8F2A"), printed
in fixer ink directly on the silver. It costs nothing, it is unfakeable structure
(the machine's provenance is literally stamped on the paper), and it makes WIRE's
prints recognisably different from any card in any other feed app.

Adopted: the `Print` primitive in `packages/ui` accepts a `caption` prop that
renders this rail; the deck, take capture, and contact sheet all use it.
