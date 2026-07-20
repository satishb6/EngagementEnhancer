"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useEffect } from "react";
import { getToken } from "@/lib/api";
import { springs, Wire } from "@/components/ui/primitives";
import { WireTicker } from "@/components/shell/WireTicker";

const ROOMS = [
  { href: "/wire", label: "Wire" },
  { href: "/darkroom", label: "Darkroom" },
  { href: "/prints", label: "Prints" },
  { href: "/studio", label: "Studio" },
] as const;

const MACHINE_VIEWS = [
  { href: "/room", label: "Wire Room" },
  { href: "/lattice", label: "Lattice" },
  { href: "/dashboard", label: "Dashboard" },
] as const;

export default function RoomsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/signin");
  }, [router]);

  return (
    <div className="flex min-h-screen flex-col">
      <WireTicker />
      <header className="flex items-center gap-8 border-b border-rule bg-selenium px-8">
        <Link href="/wire" className="wire-label py-4 font-semibold text-silver">
          WIRE
        </Link>
        <nav className="flex gap-2">
          {ROOMS.map((room) => {
            const active = pathname.startsWith(room.href);
            return (
              <Link
                key={room.href}
                href={room.href}
                className={`relative px-4 py-4 text-label ${
                  active ? "text-silver" : "text-silver-dim/70 hover:text-silver"
                }`}
              >
                {room.label}
                {active ? (
                  <motion.span
                    layoutId="room-underline"
                    transition={springs.settle}
                    className="absolute inset-x-3 bottom-0 h-[2px] bg-safelight"
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {MACHINE_VIEWS.map((view) => {
            const active = pathname.startsWith(view.href);
            return (
              <Link key={view.href} href={view.href} className="px-3 py-4">
                <Wire tone={active ? "hot" : "machine"}>{view.label}</Wire>
              </Link>
            );
          })}
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
