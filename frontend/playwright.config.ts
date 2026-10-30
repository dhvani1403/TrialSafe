import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against a live stack (API on :8000 with ingested data, web on :3000).
// Start both (`make api`, `make web`) and run `npm run test:e2e`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  workers: 2, // the dev server compiles pages on first hit
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
});
