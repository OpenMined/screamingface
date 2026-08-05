import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx}"],
    ignores: ["src/lib/uuid.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.type='MemberExpression'][callee.property.name='randomUUID']",
          message:
            "Use createUuid from '@/lib/uuid' so UUID generation works in insecure WebView contexts.",
        },
        {
          selector:
            "CallExpression[callee.type='MemberExpression'][callee.computed=true][callee.property.value='randomUUID']",
          message:
            "Use createUuid from '@/lib/uuid' so UUID generation works in insecure WebView contexts.",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
