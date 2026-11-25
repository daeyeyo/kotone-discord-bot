import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["node:sqlite"],
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
