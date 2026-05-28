import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // VYUHA_API_URL is read at runtime by src/app/api/proxy/[...path]/route.ts
  // — no need to bake it at build time via env here.
};

export default nextConfig;
