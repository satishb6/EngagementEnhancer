"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError, setToken } from "@/lib/api";
import { RedactionText, SafelightButton, Wire } from "@/components/ui/primitives";

export default function SignUp() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.signup(email, password, name);
      setToken(res.token);
      router.push("/onboarding");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something broke. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <Wire tone="dim">50 briefings a day · your voice</Wire>
        <h1 className="mb-10 mt-2 text-display">
          <RedactionText grade={35}>Start your wire</RedactionText>
        </h1>
        <div className="flex flex-col gap-4">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="name (optional)"
            className="rounded-chrome bg-selenium px-5 py-3 text-body text-silver outline-none placeholder:text-silver-dim/40 focus:bg-selenium-2"
          />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            className="rounded-chrome bg-selenium px-5 py-3 text-body text-silver outline-none placeholder:text-silver-dim/40 focus:bg-selenium-2"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void submit()}
            placeholder="password (8+ characters)"
            className="rounded-chrome bg-selenium px-5 py-3 text-body text-silver outline-none placeholder:text-silver-dim/40 focus:bg-selenium-2"
          />
          {error ? <p className="text-label text-spike">{error}</p> : null}
          <SafelightButton big onClick={() => void submit()} disabled={busy}>
            {busy ? "Creating" : "Create account"}
          </SafelightButton>
          <p className="mt-4 text-center text-label text-silver-dim">
            Already wired?{" "}
            <Link href="/signin" className="text-safelight">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
