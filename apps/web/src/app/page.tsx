"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ensureGuest, getToken } from "@/lib/api";
import { Wire } from "@/components/ui/primitives";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    void (async () => {
      if (getToken()) {
        router.replace("/wire");
        return;
      }
      // no sign-in wall: mint a guest session and walk straight in
      await ensureGuest();
      router.replace("/onboarding");
    })();
  }, [router]);
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Wire tone="machine">opening the wire…</Wire>
    </div>
  );
}
