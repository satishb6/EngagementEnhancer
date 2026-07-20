"use client";

import dynamic from "next/dynamic";
import { Wire } from "@/components/ui/primitives";

const Lattice = dynamic(
  () => import("@/components/lattice/Lattice").then((m) => m.Lattice),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-96 items-center justify-center">
        <Wire tone="machine">warming the emulsion…</Wire>
      </div>
    ),
  },
);

export default function LatticePage() {
  return <Lattice />;
}
