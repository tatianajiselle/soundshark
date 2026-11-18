import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@supabase/supabase-js": fileURLToPath(new URL("./src/cosmograph/noTelemetry.ts", import.meta.url)),
      "gl-bench": fileURLToPath(new URL("./node_modules/gl-bench/dist/gl-bench.module.js", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    target: "es2022",
    chunkSizeWarningLimit: 6000,
  },
  preview: {
    headers: {
      "Content-Security-Policy": process.env.EXPLORER_CSP ?? contentSecurityPolicy,
    },
  },
  test: {
    include: ["src/**/*.test.ts", "scripts/**/*.test.ts"],
    environment: "node",
  },
});
