import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/ch4/v3",
  images: { unoptimized: true },
};

export default nextConfig;
