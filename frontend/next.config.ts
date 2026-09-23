import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // self-contained server build for the Docker image
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  serverExternalPackages: [],
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
      // Build assets carry a content hash in their filename, so they can be
      // cached forever — a new build produces new filenames.
      {
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      // Everything else — the HTML documents above all — must be revalidated
      // (23 Sep 2026). With no cache headers at all, browsers applied
      // heuristic caching to the app shell: after a deploy, users kept an old
      // document pointing at old chunks, so shipped changes only appeared
      // after a hard refresh. Hashed assets are excluded so they stay
      // immutable.
      {
        source: "/((?!_next/static|_next/image).*)",
        headers: [
          { key: "Cache-Control", value: "no-store, must-revalidate" },
        ],
      },
    ];
  },
};

export default nextConfig;
