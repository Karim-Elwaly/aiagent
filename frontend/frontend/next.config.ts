import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8001/api/:path*",
      },
      {
        source: "/auth/:path*",
        destination: "http://127.0.0.1:8001/auth/:path*",
      },
      {
        source: "/stream/:path*",
        destination: "http://127.0.0.1:8001/stream/:path*",
      },
      {
        source: "/status/:path*",
        destination: "http://127.0.0.1:8001/status/:path*",
      },
      {
        source: "/approve/:path*",
        destination: "http://127.0.0.1:8001/approve/:path*",
      },
      {
        source: "/cancel/:path*",
        destination: "http://127.0.0.1:8001/cancel/:path*",
      },
      {
        source: "/solve/:path*",
        destination: "http://127.0.0.1:8001/solve/:path*",
      },
      {
        source: "/solve",
        destination: "http://127.0.0.1:8001/solve",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8001/health",
      },
      {
        source: "/tools",
        destination: "http://127.0.0.1:8001/tools",
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
