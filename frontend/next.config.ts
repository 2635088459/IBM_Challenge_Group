import type { NextConfig } from "next";

// Where the Next server forwards /api/* — the compose service name by default.
// Read at build time; set BACKEND_URL=http://localhost:8000 for `npm run dev` outside Docker.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // The browser only ever talks to this origin; the backend stays private
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  experimental: {
    // Agent runs call the LLM twice — allow well past the 30 s default
    proxyTimeout: 120_000,
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
