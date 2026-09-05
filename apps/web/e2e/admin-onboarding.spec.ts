import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Phase 8.1 — parcours d'onboarding admin réel : REGISTER -> LOGIN -> détermination du contexte
// école -> DASHBOARD -> SETUP WIZARD. Couvre le bug corrigé : un admin créé par /register a un
// rôle scopé organisation (pas école) — voir docs/phases/PHASE_8_1_ADMIN_CONTEXT_FIX.md.
//
// Test A ci-dessous est LE parcours critique demandé : exécuté contre l'API + Postgres réels
// (docker compose), sans aucun mock. Les tests C (erreur réseau) utilisent délibérément et
// explicitement une interception Playwright ciblée pour provoquer une panne précise et vérifier
// l'état d'erreur — ce n'est pas le parcours critique et c'est indiqué clairement.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";

function unique(prefix: string): string {
  return `${prefix}${Date.now()}${Math.floor(Math.random() * 10000)}`;
}

async function registerOrgAdmin(page: Page, slugPrefix: string) {
  const slug = unique(slugPrefix).toLowerCase();
  const email = `${slug}@wizard-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Org Admin");
  await page.getByPlaceholder("Votre email").fill(email);
  await page.getByPlaceholder("Mot de passe (8 caractères min.)").fill(password);
  await page.getByRole("button", { name: "Créer mon compte" }).click();

  return { slug, email, password };
}

test("CRITIQUE (réel, sans mock) — nouvel admin : register -> login -> dashboard -> setup wizard", async ({
  page,
}) => {
  await registerOrgAdmin(page, "onboard");

  // register() enchaîne déjà un login réel (voir apps/web/app/(auth)/register/page.tsx) : on est
  // donc immédiatement sur le dashboard, authentifié pour de vrai.
  await expect(page).toHaveURL("/");

  // Avant le correctif Phase 8.1 : ceci restait bloqué indéfiniment sur "Chargement..." (le rôle
  // scopé organisation de cet admin n'était jamais résolu en école courante).
  await expect(page.getByText("Chargement...")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  await page.getByRole("link", { name: "Mise en place" }).click();
  await expect(page).toHaveURL("/setup");
  await expect(page.getByRole("heading", { name: "Mise en place de l'école" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Année scolaire" })).toBeVisible();
});

test.describe("Plusieurs écoles pour la même organisation", () => {
  async function createSecondSchool(page: Page, request: APIRequestContext, email: string, password: string) {
    const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
    const { access_token: token } = await loginResponse.json();

    const meResponse = await request.get(`${API_BASE_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const me = await meResponse.json();
    const orgId: string = me.roles[0].organization_id;

    const slug = unique("secondschool").toLowerCase();
    const createResponse = await request.post(`${API_BASE_URL}/api/v1/schools`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { organization_id: orgId, name: `Ecole B ${slug}`, slug },
    });
    return createResponse.json();
  }

  test("admin avec 2 écoles : sélection explicite requise, jamais arbitraire, puis mémorisée", async ({
    page,
    request,
  }) => {
    const { email, password } = await registerOrgAdmin(page, "multi");
    await expect(page).toHaveURL("/");

    const secondSchool = await createSecondSchool(page, request, email, password);

    // Nouvelle session (localStorage vidé) : simule une reconnexion après la création de la
    // seconde école, pour repartir d'un état de résolution propre.
    await page.evaluate(() => window.localStorage.clear());
    await page.goto("/login");
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Mot de passe").fill(password);
    await page.getByRole("button", { name: "Se connecter" }).click();

    // Jamais de sélection arbitraire : l'assistant de sélection s'affiche, pas le dashboard.
    await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
    await expect(page.getByRole("button", { name: secondSchool.name })).toBeVisible();

    await page.getByRole("button", { name: secondSchool.name }).click();
    await expect(page.getByText("Choisissez une école")).toHaveCount(0);
    await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

    // Le choix est mémorisé : un rechargement ne redemande pas la sélection.
    await page.reload();
    await expect(page.getByText("Choisissez une école")).toHaveCount(0);
    await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
  });
});

test("erreur lors de la détermination du contexte école : message clair, jamais de blocage silencieux, réessai possible", async ({
  page,
}) => {
  // Interception ciblée et explicite (documentée ci-dessus) : seule cette requête précise échoue,
  // pour vérifier l'état d'erreur — ce n'est pas le parcours critique (celui-ci est 100% réel,
  // voir le test précédent).
  let shouldFail = true;
  await page.route("**/api/v1/schools?organization_id=*", (route) => {
    if (shouldFail) {
      return route.abort("failed");
    }
    return route.continue();
  });

  await registerOrgAdmin(page, "resolveerr");
  await expect(page).toHaveURL("/");

  // getByRole("alert") remonterait aussi le route-announcer interne de Next.js
  // (#__next-route-announcer__, role="alert" lui aussi) — on cible donc le texte exact.
  await expect(page.getByText("Erreur réseau : vérifiez votre connexion et réessayez.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Se reconnecter" })).toBeVisible();

  shouldFail = false;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});
