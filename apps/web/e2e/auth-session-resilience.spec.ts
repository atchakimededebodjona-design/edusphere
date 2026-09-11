import { expect, test, type Page } from "@playwright/test";

// Phase 27 Sprint 1.1 — Auth & Session Resilience (voir
// docs/phases/PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md). Ce projet n'a pas de runner de test
// unitaire JS (aucun Jest/Vitest configuré, confirmé avant d'écrire ce fichier) : les scénarios
// listés dans la mission comme "tests unitaires" sont donc couverts ici, comme tests E2E, au même
// titre que les scénarios explicitement E2E — cohérent avec l'architecture de test déjà en place
// dans ce dépôt (Playwright uniquement côté Web).
//
// Convention déjà établie par admin-onboarding.spec.ts : parcours réel contre l'API + Postgres
// (docker compose), sans mock, SAUF quand un scénario a spécifiquement besoin d'observer ou de
// provoquer un événement réseau précis (comptage d'appels, coupure réseau) — dans ce cas,
// `page.route()` est utilisé de façon ciblée et documentée, jamais pour remplacer le parcours
// d'authentification réel lui-même.

const LEGACY_KEY = "edusphere.session";
const CURRENT_KEY = "edulinkage.session";

function unique(prefix: string): string {
  return `${prefix}${Date.now()}${Math.floor(Math.random() * 10000)}`;
}

async function registerRealAccount(page: Page, slugPrefix: string) {
  const slug = unique(slugPrefix).toLowerCase();
  const email = `${slug}@auth-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Auth E2E Admin");
  await page.getByPlaceholder("Votre email").fill(email);
  await page.getByPlaceholder("Mot de passe (8 caractères min.)").fill(password);
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  return { slug, email, password };
}

async function readSession(page: Page, key: string): Promise<{ access_token: string; refresh_token: string } | null> {
  const raw = await page.evaluate((k) => window.localStorage.getItem(k), key);
  return raw ? JSON.parse(raw) : null;
}

// --- A/B/C/D/F/G (migration douce, ancienne clé) ---------------------------------------------

test("session valide sous la nouvelle clé : aucune différence de comportement", async ({ page }) => {
  await registerRealAccount(page, "newkey");
  const session = await readSession(page, CURRENT_KEY);
  expect(session?.access_token).toBeTruthy();
  await page.reload();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

test("ancienne clé edusphere.session valide : migrée vers edulinkage.session, utilisateur reste connecté", async ({
  page,
}) => {
  await registerRealAccount(page, "legacykey");
  const realSession = await readSession(page, CURRENT_KEY);
  expect(realSession).not.toBeNull();

  // Simule un navigateur qui possédait encore une session valide sous l'ANCIENNE clé au moment du
  // déploiement (scénario réel de l'incident documenté dans la Discovery) : les tokens sont
  // authentiques (émis par le vrai backend juste au-dessus), seule la clé de stockage est ancienne.
  await page.evaluate(
    ({ key, value }) => {
      window.localStorage.removeItem("edulinkage.session");
      window.localStorage.setItem(key, JSON.stringify(value));
    },
    { key: LEGACY_KEY, value: realSession },
  );

  await page.reload();

  // L'utilisateur reste connecté sans aucune reconnexion manuelle : la page fonctionne normalement.
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  // La migration a bien eu lieu : nouvelle clé présente, ancienne supprimée.
  const migrated = await readSession(page, CURRENT_KEY);
  const legacyAfter = await page.evaluate((k) => window.localStorage.getItem(k), LEGACY_KEY);
  expect(migrated?.access_token).toBe(realSession!.access_token);
  expect(legacyAfter).toBeNull();
});

test("ancienne clé edusphere.session malformée : traité comme non authentifié, pas de crash", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate((key) => window.localStorage.setItem(key, "{ceci n'est pas du JSON"), LEGACY_KEY);

  await page.goto("/");

  // Aucun bypass : un JSON invalide sous l'ancienne clé n'authentifie jamais personne.
  await expect(page).toHaveURL(/\/login$/);
});

// --- E (401 + refresh valide → retry) -----------------------------------------------------------

test("access token invalide + refresh token réel valide : rafraîchissement silencieux, page fonctionne", async ({
  page,
}) => {
  await registerRealAccount(page, "refreshok");
  const realSession = await readSession(page, CURRENT_KEY);

  // Un access_token structurellement invalide (jamais émis par le serveur) produit exactement le
  // même 401 "Could not validate credentials" qu'un access_token réellement expiré (voir
  // Discovery §3 : jwt.InvalidTokenError couvre les deux cas) — le refresh_token, lui, est
  // authentique et valide, donc le refresh qui suit est un VRAI appel réussi contre le VRAI
  // backend, pas une simulation.
  await page.evaluate(
    ({ key, refresh_token }) => {
      window.localStorage.setItem(key, JSON.stringify({ access_token: "not-a-real-token", refresh_token }));
    },
    { key: CURRENT_KEY, refresh_token: realSession!.refresh_token },
  );

  await page.reload();

  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  // Le rafraîchissement a bien eu lieu : le nouvel access_token stocké n'est plus le token invalide.
  const afterRefresh = await readSession(page, CURRENT_KEY);
  expect(afterRefresh?.access_token).not.toBe("not-a-real-token");
});

// --- F/J (refresh invalide → session nettoyée, AuthProvider informé, redirection) ----------------

test("access token ET refresh token invalides : session nettoyée, redirection propre vers /login", async ({
  page,
}) => {
  await registerRealAccount(page, "refreshko");

  await page.evaluate((key) => {
    window.localStorage.setItem(key, JSON.stringify({ access_token: "bad.token", refresh_token: "bad-refresh" }));
  }, CURRENT_KEY);

  await page.reload();

  // Redirection réellement effective (pas seulement une erreur affichée sur place) : AuthProvider
  // a bien été informé de l'échec définitif du refresh (voir onSessionExpired, api/client.ts).
  await expect(page).toHaveURL(/\/login$/, { timeout: 10_000 });

  // Session nettoyée : rien ne subsiste sous aucune des deux clés.
  const current = await page.evaluate((k) => window.localStorage.getItem(k), CURRENT_KEY);
  const legacy = await page.evaluate((k) => window.localStorage.getItem(k), LEGACY_KEY);
  expect(current).toBeNull();
  expect(legacy).toBeNull();

  // Jamais le message technique brut du backend affiché comme erreur finale.
  await expect(page.getByText("Could not validate credentials")).toHaveCount(0);
});

// --- H/G (401 simultanés → un seul refresh, pas de boucle) --------------------------------------

test("plusieurs requêtes 401 simultanées (dashboard) : un seul appel réel à /auth/refresh", async ({ page }) => {
  await registerRealAccount(page, "concurrent");
  const realSession = await readSession(page, CURRENT_KEY);

  let refreshCallCount = 0;
  // Interception ciblée : laisse la requête réelle passer (route.continue()), compte simplement
  // combien de fois elle est effectivement envoyée — ne remplace jamais la vraie logique serveur.
  await page.route("**/api/v1/auth/refresh", (route) => {
    refreshCallCount += 1;
    return route.continue();
  });

  await page.evaluate(
    ({ key, refresh_token }) => {
      window.localStorage.setItem(key, JSON.stringify({ access_token: "not-a-real-token", refresh_token }));
    },
    { key: CURRENT_KEY, refresh_token: realSession!.refresh_token },
  );

  // Le tableau de bord (page "/") déclenche deux appels API authentifiés en parallèle au montage
  // (école + indicateurs, voir apps/web/app/(app)/page.tsx) — les deux reçoivent 401 quasi
  // simultanément avec le token invalide ci-dessus.
  await page.goto("/");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  expect(refreshCallCount).toBe(1);
});

// --- I (erreur réseau pendant le refresh ≠ session expirée) --------------------------------------

test("coupure réseau pendant le refresh (app déjà authentifiée) : session locale NON détruite, pas de déconnexion", async ({
  page,
}) => {
  // Distinct du test précédent : ici l'app est déjà montée et authentifiée (AuthProvider.status
  // == "authenticated") AVANT que le token ne soit corrompu — on ne passe donc jamais par
  // AuthProvider::loadMe() (chargement initial), seulement par apiFetch depuis une navigation
  // cliente normale, ce qui isole précisément le comportement de requestRefresh() face à une
  // NetworkError (voir api/client.ts) sans le mélanger avec le chargement initial de la page.
  await registerRealAccount(page, "netfail");
  const realSession = await readSession(page, CURRENT_KEY);

  // Corrompt l'access_token en place, sans recharger la page : AuthProvider reste "authenticated".
  await page.evaluate(
    ({ key, refresh_token }) => {
      window.localStorage.setItem(key, JSON.stringify({ access_token: "not-a-real-token", refresh_token }));
    },
    { key: CURRENT_KEY, refresh_token: realSession!.refresh_token },
  );

  await page.route("**/api/v1/auth/refresh", (route) => route.abort("failed"));

  // Navigation cliente (pas de reload) vers un écran qui déclenche un nouvel appel API authentifié.
  // Sélecteur scopé au menu latéral (<nav>, rôle "navigation") : "Notifications" existe aussi comme
  // lien-icône dans le TopBar (<header>, aria-label="Notifications") — les deux sont des éléments
  // légitimes et préexistants de l'UI, `getByRole("navigation")` cible sans ambiguïté le second.
  await page.getByRole("navigation").getByRole("link", { name: "Notifications" }).click();
  await page.waitForTimeout(1000);

  // Pas de redirection forcée vers /login : une coupure réseau pendant le refresh n'est jamais
  // traitée comme une session définitivement invalide.
  await expect(page).not.toHaveURL(/\/login$/);

  // Session locale intacte : même refresh_token qu'avant la tentative de rafraîchissement échouée.
  const afterNetworkFailure = await readSession(page, CURRENT_KEY);
  expect(afterNetworkFailure?.refresh_token).toBe(realSession!.refresh_token);
});
