"use client";

// The sign-up wall is gone: WIRE is anonymous-first. Anyone landing on the
// old URL walks straight in as a guest.

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SignUp() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
