import { defineConfig } from "@playwright/test";

export const SEEDED = "http://127.0.0.1:4173";
export const EMPTY = "http://127.0.0.1:4174";

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: SEEDED,
    acceptDownloads: true,
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    { command: "scripts/start_backend.sh 8101 seeded", url: "http://127.0.0.1:8101/health", reuseExistingServer: false, timeout: 120_000 },
    { command: "scripts/start_backend.sh 8102 empty", url: "http://127.0.0.1:8102/health", reuseExistingServer: false, timeout: 120_000 },
    { command: "scripts/start_frontend.sh 4173 8101", url: SEEDED, reuseExistingServer: false, timeout: 60_000 },
    { command: "scripts/start_frontend.sh 4174 8102", url: EMPTY, reuseExistingServer: false, timeout: 60_000 },
  ],
});
