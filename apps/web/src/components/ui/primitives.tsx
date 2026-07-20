"use client";

/**
 * The design system primitives. docs/DESIGN.md is binding:
 * Print — the silver content surface (cut corners, top highlight, shadow)
 * Chrome — dark machine surface (tone separation, no shadow)
 * Wire — the mono instrument label
 * RedactionText — display type whose halftone grade is a prop
 */

import { motion, useReducedMotion } from "framer-motion";
import type { HTMLAttributes, ReactNode } from "react";
import { spring } from "../../../../../packages/shared/tokens";

export function Print({
  children,
  caption,
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement> & { caption?: string }) {
  return (
    <div className={`print-surface ${className}`} {...rest}>
      {children}
      {caption ? (
        <div className="wire-label border-t border-ink/10 px-5 py-2 text-fixer">
          {caption}
        </div>
      ) : null}
    </div>
  );
}

export function Chrome({
  children,
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`chrome-surface ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function Wire({
  children,
  tone = "dim",
  className = "",
}: {
  children: ReactNode;
  tone?: "dim" | "human" | "machine" | "hot" | "reject";
  className?: string;
}) {
  const tones = {
    dim: "text-silver-dim/60",
    human: "text-safelight",
    machine: "text-fixer",
    hot: "text-fixer-hot",
    reject: "text-spike",
  } as const;
  return (
    <span className={`wire-label ${tones[tone]} ${className}`}>{children}</span>
  );
}

/**
 * Redaction display text. grade 10 = machine-made, 35 = briefing,
 * 100 = human. `animateToHuman` runs the 10 → 100 transition as a
 * continuous progress value while the user edits.
 */
export function RedactionText({
  children,
  grade = 35,
  progress,
  className = "",
}: {
  children: ReactNode;
  grade?: 10 | 35 | 100;
  /** 0..1: interpolate the grade from 10 to 100 (editing takeover). */
  progress?: number;
  className?: string;
}) {
  if (progress !== undefined) {
    const p = Math.min(Math.max(progress, 0), 1);
    return (
      <span
        className={`font-display ${className}`}
        style={{
          opacity: 0.82 + 0.18 * p,
          filter: `contrast(${1.35 - 0.35 * p}) blur(${0.24 * (1 - p)}px)`,
          transition: "opacity 200ms, filter 200ms",
        }}
      >
        {children}
      </span>
    );
  }
  const cls = grade === 10 ? "grade-10" : grade === 100 ? "grade-100" : "grade-35";
  return <span className={`font-display ${cls} ${className}`}>{children}</span>;
}

/** The develop reveal — briefings and finished content only. */
export function Develop({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <div className={`${reduced ? "" : "develop-in"} ${className}`}>{children}</div>
  );
}

/** Named springs from the tokens, as framer transition objects. */
export const springs = {
  snap: { type: "spring" as const, ...spring.snap },
  settle: { type: "spring" as const, ...spring.settle },
  develop: { type: "spring" as const, ...spring.develop },
};

export function SafelightButton({
  children,
  onClick,
  disabled,
  className = "",
  big = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  big?: boolean;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      transition={springs.snap}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-chrome bg-safelight font-sans font-semibold text-ink
        disabled:opacity-40 ${big ? "px-10 py-4 text-body" : "px-6 py-2 text-label"} ${className}`}
    >
      {children}
    </motion.button>
  );
}

export function ChromeButton({
  children,
  onClick,
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      transition={springs.snap}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-chrome bg-selenium px-6 py-2 font-sans text-label
        text-silver hover:bg-selenium-2 disabled:opacity-40 ${className}`}
    >
      {children}
    </motion.button>
  );
}
