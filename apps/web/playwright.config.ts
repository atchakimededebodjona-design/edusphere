import { defineConfig, devices } from "@playwright/test";

// L'API + Postgres (docker compose ou local) doivent déjà tourner pour les tests qui vont
// au-delà des pages statiques (login réel, etc.) — Playwright ne gère que le process web ici.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
