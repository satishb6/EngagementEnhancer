import type { Config } from "tailwindcss";
import {
  color,
  radius,
  rule,
  shadow,
  space,
} from "../../packages/shared/tokens";

/**
 * Token bridge: Tailwind reads packages/shared/tokens.ts. No colour, radius,
 * or shadow exists here that isn't in the design tokens.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      graphite: color.graphite,
      "graphite-2": color.graphite2,
      selenium: color.selenium,
      "selenium-2": color.selenium2,
      silver: color.silver,
      "silver-dim": color.silverDim,
      safelight: color.safelight,
      fixer: color.fixer,
      "fixer-hot": color.fixerHot,
      spike: color.spike,
      ink: color.ink,
      "ink-soft": color.inkSoft,
    },
    borderColor: ({ theme }) => ({
      ...theme("colors"),
      rule: rule.faint,
      "rule-strong": rule.strong,
    }),
    borderRadius: {
      none: "0",
      print: `${radius.print}px`,
      chrome: `${radius.chrome}px`,
      full: "9999px",
    },
    boxShadow: {
      none: "none",
      print: shadow.print,
      lifted: shadow.lifted,
    },
    spacing: Object.fromEntries(
      Object.entries(space).map(([k, v]) => [k, `${v}px`]),
    ),
    fontFamily: {
      display: ["Redaction", "Instrument Serif", "Georgia", "serif"],
      sans: ["Instrument Sans", "system-ui", "sans-serif"],
      mono: ["Martian Mono", "ui-monospace", "monospace"],
    },
    extend: {
      fontSize: {
        "display-xl": ["56px", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
        display: ["40px", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
        briefing: ["28px", { lineHeight: "1.35" }],
        body: ["17px", { lineHeight: "1.6", letterSpacing: "-0.011em" }],
        label: ["14px", { lineHeight: "1.4", letterSpacing: "-0.011em" }],
        wire: ["11px", { lineHeight: "1.4", letterSpacing: "0.08em" }],
      },
    },
  },
  plugins: [],
};

export default config;
