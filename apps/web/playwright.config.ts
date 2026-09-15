import { defineConfig, devices } from "@playwright/test";

// L'API + Postgres (docker compose ou local) doivent déjà tourner pour les tests qui vont
// au-delà des pages statiques (login réel, etc.) — Playwright ne gère que le process web ici.
//
// `PLAYWRIGHT_WEB_BASE_URL` : additif, jamais requis — absent, le comportement reste strictement
// celui d'avant (http://localhost:3000). Permet d'exécuter la suite depuis un conteneur qui ne
// peut pas atteindre le "localhost" publié par Docker Desktop sur l'hôte (ex. validation isolée
// d'une image web jetable dans le même réseau compose), sans toucher au comportement par défaut.
const webBaseURL = process.env.PLAYWRIGHT_WEB_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: webBaseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev",
    url: webBaseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
