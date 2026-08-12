import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: { root: __dirname },
  async rewrites() {
    const apiOrigin = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";
    return [{ source: "/api/v1/:path*", destination: `${apiOrigin}/:path*` }];
  },
};

export default nextConfig;
