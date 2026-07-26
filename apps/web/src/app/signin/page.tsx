"use client";

// The sign-in wall is gone: WIRE is anonymous-first. Anyone landing on the
// old URL walks straight in as a guest.

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SignIn() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
