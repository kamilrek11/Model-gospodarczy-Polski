/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API_TARGET lets e2e/preview point the /api proxy at another backend (default: local dev backend).
declare const process: { env: Record<string, string | undefined> };
const api = {
  "/api": {
    target: process.env.API_TARGET ?? "http://localhost:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  // Recharts dominates the main chunk (~650 kB); jsPDF is lazy-loaded in its own chunk.
  build: { chunkSizeWarningLimit: 700 },
  server: { proxy: api },
  preview: { proxy: api },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    // styles.css is read as text (?raw) by the colour-contrast test; other CSS stays stubbed.
    css: { include: [/styles\.css/] },
  },
});
