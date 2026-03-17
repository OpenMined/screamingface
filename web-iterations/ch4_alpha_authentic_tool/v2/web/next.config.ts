import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/ch4/v2",
  images: { unoptimized: true },
};

export default nextConfig;
