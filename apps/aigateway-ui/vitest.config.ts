import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      // `cobertura` is what orgoro/coverage@v3.2 reads in CI — the same action the Python lanes
      // use. `text` keeps the local run readable without opening a file.
      reporter: ["text", "cobertura"],
      include: ["src/**"],
      // The root layout declares three next/font loaders and a metadata object and returns a
      // fixed wrapper — no branch, no logic, nothing a unit test could hold. Rendering it in
      // jsdom would also nest <html>/<body> inside a document, which React rejects. `next build`
      // is what proves it: a bad font loader or a malformed metadata export fails the build.
      // Everything with behaviour stays inside the threshold.
      exclude: [
        "src/app/layout.tsx",
        // Generated type declarations from aigateway's OpenAPI — no runtime code at all,
        // so it can only ever report 0% and drag the real number down.
        "src/lib/aigateway/schema.d.ts",
        // Vendored OMDS tokens; upstream's code, not ours to test.
        "src/brand/**",
      ],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
