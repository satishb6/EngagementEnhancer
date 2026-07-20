import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["three"],
  eslint: { ignoreDuringBuilds: false },
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [{ source: "/api/wire/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
