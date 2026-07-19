/**
 * WIRE design tokens — the single source of truth.
 * Both apps import from here. docs/DESIGN.md is the binding spec;
 * this file is its typed projection. Do not add values that aren't in the doc.
 */

/* ---------------------------------- colour --------------------------------- */

export const color = {
  /** The room. App ground, edge to edge. */
  graphite: '#12161B',
  /** Slightly lifted ground for framed regions (derived from graphite). */
  graphite2: '#171C23',
  /** Raised machine surfaces — nav, sheets, controls. */
  selenium: '#1E262F',
  /** Hover/active machine surface (derived from selenium). */
  selenium2: '#27313C',
  /** The print. Every piece of readable content sits on this. */
  silver: '#DAD5C9',
  /** Secondary text on graphite (derived from silver). */
  silverDim: '#B5AFA2',
  /** You. Every human action: swipe right, your opinion, publish, select. */
  safelight: '#FF8A3D',
  /** The machine. Extraction, generation, AI states, graph structure. */
  fixer: '#6D64A3',
  /** Active machine state only — a job actually running, a node selected. */
  fixerHot: '#9A8EE0',
  /** Reject. Left-swipe, discard, destructive. */
  spike: '#C4453C',
  /** Ink — text on the silver print surface. */
  ink: '#0C0F13',
  /** Body text on the print surface. */
  inkSoft: '#3A4048',
} as const;

export type ColorToken = keyof typeof color;

/** Hairline rules on dark ground. Derived from silver, never a framework grey. */
export const rule = {
  faint: 'rgba(218,213,201,0.12)',
  strong: 'rgba(218,213,201,0.24)',
} as const;

/* ----------------------------------- type ---------------------------------- */

export const fontFamily = {
  /** Display. Briefing headlines, screen titles, the big moments. */
  display: "'Redaction', 'Instrument Serif', Georgia, serif",
  /** Interface. Buttons, labels, body, navigation. */
  sans: "'Instrument Sans', system-ui, sans-serif",
  /** The wire. Anything the machine measured. Uppercase, tracked, small. */
  mono: "'Martian Mono', ui-monospace, monospace",
} as const;

/**
 * Redaction halftone grades carry meaning:
 * 100 (finest)  — human-authored text
 *  35           — briefings; journalism, processed but faithful
 *  10 (coarsest)— AI-generated copy, before you've touched it
 */
export const redactionGrade = {
  human: 100,
  briefing: 35,
  machine: 10,
} as const;

export type RedactionGrade =
  (typeof redactionGrade)[keyof typeof redactionGrade];

export interface TypeStyle {
  /** px on mobile */
  mobile: number;
  /** px on web */
  web: number;
  family: keyof typeof fontFamily;
  /** unitless line-height */
  leading: number;
  /** em */
  tracking: number;
  weight: number;
  uppercase?: boolean;
}

export const typeScale = {
  displayXl: {
    mobile: 40, web: 56, family: 'display', leading: 1.05, tracking: -0.02, weight: 400,
  },
  display: {
    mobile: 30, web: 40, family: 'display', leading: 1.1, tracking: -0.02, weight: 400,
  },
  briefing: {
    mobile: 22, web: 28, family: 'display', leading: 1.35, tracking: 0, weight: 400,
  },
  body: {
    mobile: 16, web: 17, family: 'sans', leading: 1.6, tracking: -0.011, weight: 400,
  },
  label: {
    mobile: 13, web: 14, family: 'sans', leading: 1.4, tracking: -0.011, weight: 500,
  },
  wire: {
    mobile: 10, web: 11, family: 'mono', leading: 1.4, tracking: 0.08, weight: 400, uppercase: true,
  },
} as const satisfies Record<string, TypeStyle>;

export type TypeScaleToken = keyof typeof typeScale;

/* --------------------------------- spacing --------------------------------- */

/** 4px base. Use steps, never arbitrary pixel values. */
export const space = {
  0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64, 20: 80, 24: 96,
} as const;

export type SpaceToken = keyof typeof space;

/* ---------------------------------- radii ---------------------------------- */

export const radius = {
  /** Print surfaces: paper is cut, not rounded. */
  print: 3,
  /** Machine chrome. */
  chrome: 10,
  /** Fully round (avatars, particles, the timeline thumb). */
  full: 9999,
} as const;

/* --------------------------------- shadows --------------------------------- */

export const shadow = {
  /** The print's real shadow. */
  print: '0 24px 48px -12px rgba(0,0,0,0.7)',
  /** A lifted card mid-drag. */
  lifted: '0 32px 64px -16px rgba(0,0,0,0.8)',
  /** Machine chrome carries no shadow: separated by tone, not elevation. */
  none: 'none',
} as const;

/** 1px inner highlight at 6% white on the top edge of every print. */
export const printHighlight = 'rgba(255,255,255,0.06)';

/** Grain: 2–3% opacity noise overlay across the entire app, always. */
export const grainOpacity = 0.03;

/* ---------------------------------- motion --------------------------------- */

export interface SpringConfig {
  stiffness: number;
  damping: number;
}

/** Springs, not easings. Everything interruptible. */
export const spring = {
  /** Taps, toggles. */
  snap: { stiffness: 400, damping: 30 },
  /** Cards landing, sheets. */
  settle: { stiffness: 220, damping: 26 },
  /** The print-development reveal. Briefings and finished content only. */
  develop: { stiffness: 90, damping: 20 },
} as const satisfies Record<string, SpringConfig>;

export type SpringToken = keyof typeof spring;

/** Under prefers-reduced-motion all springs collapse to this. */
export const reducedMotionFadeMs = 120;

/** The develop transition duration when it runs as a keyframe sequence. */
export const developDurationMs = 700;

/* --------------------------------- semantics -------------------------------- */

/**
 * Colour encodes agency. These aliases exist so call-sites say what they
 * mean; using `color.safelight` for a machine state is a review-blocking bug.
 */
export const agency = {
  human: color.safelight,
  machine: color.fixer,
  machineActive: color.fixerHot,
  reject: color.spike,
} as const;

export const tokens = {
  color, rule, fontFamily, redactionGrade, typeScale, space, radius,
  shadow, printHighlight, grainOpacity, spring, reducedMotionFadeMs,
  developDurationMs, agency,
} as const;

export default tokens;
