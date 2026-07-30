import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // WHY "standalone" and not the studio frontend's "export": this app is a BFF. Every call to
  // aigateway's /v1/admin surface happens server-side, so that the browser never holds the admin
  // API's address and X-User-Email never has to survive a round trip through client code. A static
  // export has no server and could not do that.
  output: "standalone",
};

export default nextConfig;
