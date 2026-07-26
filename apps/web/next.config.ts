import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone needs symlinks — fine in the Linux Docker build, blocked on
  // Windows without Developer Mode. The Dockerfile sets BUILD_STANDALONE=1.
  output: process.env.BUILD_STANDALONE ? "standalone" : undefined,
  transpilePackages: ["three"],
  eslint: { ignoreDuringBuilds: false },
  async rewrites() {
    // trailing-slash-proof: "…onrender.com/" pasted into the env var must
    // not become "…onrender.com//health"
    const api = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
      .trim()
      .replace(/\/+$/, "");
    return [{ source: "/api/wire/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
