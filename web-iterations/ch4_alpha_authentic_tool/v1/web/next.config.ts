import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/ch4/v1",
  images: { unoptimized: true },
};

export default nextConfig;
