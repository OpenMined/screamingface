import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/screamingface",
  assetPrefix: "/screamingface/",
  images: { unoptimized: true },
};

export default nextConfig;
