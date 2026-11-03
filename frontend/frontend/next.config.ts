import type { NextConfig } from "next";

const FLEET_STUDIO_API = process.env.FLEET_STUDIO_API_URL || "http://127.0.0.1:8001";
const UAOS_API = process.env.UAOS_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [
      // ── 1. Fleet Studio Backend (:8001) Core Routes ──
      {
        source: "/api/v1/:path*",
        destination: `${FLEET_STUDIO_API}/api/v1/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${FLEET_STUDIO_API}/auth/:path*`,
      },
      {
        source: "/health",
        destination: `${FLEET_STUDIO_API}/health`,
      },

      // ── 2. Orchestrator Backend (:8000) Routes (Arenas, Skills, Hermes, Schedules, Streams) ──
      {
        source: "/api/fleet/:path*",
        destination: `${UAOS_API}/api/fleet/:path*`,
      },
      {
        source: "/api/skills/:path*",
        destination: `${UAOS_API}/api/skills/:path*`,
      },
      {
        source: "/api/hermes/:path*",
        destination: `${UAOS_API}/api/hermes/:path*`,
      },
      {
        source: "/api/schedules/:path*",
        destination: `${UAOS_API}/api/schedules/:path*`,
      },
      {
        source: "/api/schedules",
        destination: `${UAOS_API}/api/schedules`,
      },
      {
        source: "/stream/:path*",
        destination: `${UAOS_API}/stream/:path*`,
      },
      {
        source: "/status/:path*",
        destination: `${UAOS_API}/status/:path*`,
      },
      {
        source: "/approve/:path*",
        destination: `${UAOS_API}/approve/:path*`,
      },
      {
        source: "/cancel/:path*",
        destination: `${UAOS_API}/cancel/:path*`,
      },
      {
        source: "/solve/:path*",
        destination: `${UAOS_API}/solve/:path*`,
      },
      {
        source: "/solve",
        destination: `${UAOS_API}/solve`,
      },
      {
        source: "/tools",
        destination: `${UAOS_API}/tools`,
      },

      // ── 3. Fallback for remaining /api/* to Fleet Studio Backend ──
      {
        source: "/api/:path*",
        destination: `${FLEET_STUDIO_API}/api/:path*`,
      },
    ];
  },
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
