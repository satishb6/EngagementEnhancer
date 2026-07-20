# Visual audit — round 1 (partial, honest)

**Scope of this pass:** the app was driven in a live browser against the dev
server *without* the API running, so only the public surfaces could be
exercised: `/dev/gallery`, `/signin`, `/onboarding`. The authenticated rooms
(deck, darkroom, sheet, Wire Room, Lattice, dashboard) render only with a
live database and are covered by round 2 (below).

## Verified in this pass

- **Redaction is real.** All three grade files load with HTTP 200
  (`Redaction_10/35/100-Regular.woff2`) and the gallery's provenance ladder
  renders in the actual typeface, not the fallback serif.
- **Gallery** renders every primitive: type scale, grade ladder with the
  animated 10→100 slider, print-vs-chrome material comparison, agency
  colour chips. Zero console errors.
- **Onboarding** renders the topic swipe deck with keep/toss controls.
- **Sign-in** renders restrained, as specced.
- **Bug found and fixed during the pass:** the gallery lived at
  `/_dev/gallery`; App Router treats `_`-prefixed folders as private, so the
  route 404'd in every build until now. Moved to `/dev/gallery`.

## Known limitations to re-check in round 2 (with the API up)

1. Deck mid-drag physicality at 390px — does the shadow sell the lift?
2. Silver Print surfaces under the grain overlay — print vs "light card".
3. Grease-pencil circle stroke timing on the contact sheet at 60fps.
4. Wire Room particle honesty — genuinely dead when the pipeline is idle.
5. Lattice exposure luminance ladder against LATTICE-REFERENCE.md.
6. Reduced-motion collapse across all four rooms.

Run round 2 by: `START-WIRE.bat`, then ask Claude to "run the visual audit
against the running app" — it will screenshot every room at 390/768/1440px
and update this file.
