import { execFileSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Sélecteur de contexte organisation/école permanent dans le header (components/app-shell/
// TenantSwitcher.tsx), qui permet de changer de contexte sans déconnexion une fois déjà entré
// dans l'application. S'appuie entièrement sur AuthProvider (voir tenant-context.spec.ts pour les
// tests de la logique de résolution elle-même) : ce fichier teste seulement le composant — son
// affichage, son ouverture/fermeture, et que le changement déclenché depuis lui se propage bien
// (rechargement des pages, persistance, jamais de mélange entre organisations).
//
// Même convention que tenant-context.spec.ts (pas de runner de test unitaire JS dans ce projet,
// voir auth-session-resilience.spec.ts) et mêmes helpers, dupliqués localement à dessein — aucun
// module e2e partagé n'existe encore dans ce projet (chaque fichier reste autonome).
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";

let uniqueCounter = 0;
function unique(prefix: string): string {
  uniqueCounter += 1;
  return `${prefix}${Date.now()}${uniqueCounter}${Math.floor(Math.random() * 10000)}`;
}

function clearRegisterRateLimit(): void {
  try {
    execFileSync(
      "docker",
      [
        "compose",
        "-p",
        COMPOSE_PROJECT_NAME,
        "exec",
        "-T",
        "redis",
        "sh",
        "-c",
        "redis-cli --scan --pattern 'register_attempts:*' | xargs -r redis-cli del",
      ],
      { cwd: REPO_ROOT },
    );
  } catch {
    // Best-effort : voir tenant-context.spec.ts pour la même justification.
  }
}

test.beforeEach(() => {
  clearRegisterRateLimit();
});

/** Reproduit un compte rattaché à une seconde organisation — état qu'aucun flux produit ne permet
 * de créer lui-même (email unique à l'inscription, `POST /users` limité à l'organisation de
 * l'appelant). Voir tenant-context.spec.ts pour la justification complète. */
function assignOrganizationScopedRole(userId: string, roleCode: string, organizationId: string): void {
  const script = [
    "import asyncio, uuid",
    "from sqlalchemy import select",
    "from app.db import model_registry  # noqa: F401 -- enregistre tous les modèles ORM (FK)",
    "from app.core.tenancy import set_platform_wide_context",
    "from app.db.session import AsyncSessionLocal",
    "from app.modules.rbac.models import Role, UserRole",
    "",
    "async def main():",
    "    async with AsyncSessionLocal() as db:",
    "        await set_platform_wide_context(db)",
    `        role = (await db.execute(select(Role).where(Role.code == ${JSON.stringify(roleCode)}))).scalar_one()`,
    "        db.add(UserRole(",
    "            id=uuid.uuid4(),",
    `            user_id=uuid.UUID(${JSON.stringify(userId)}),`,
    "            role_id=role.id,",
    `            organization_id=uuid.UUID(${JSON.stringify(organizationId)}),`,
    "            school_id=None,",
    "        ))",
    "        await db.commit()",
    "",
    "asyncio.run(main())",
  ].join("\n");

  const tmpFile = path.join(os.tmpdir(), `assign_role_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerPath = `/app/assign_role_e2e_${unique("")}.py`;
  try {
    execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "cp", tmpFile, `api:${containerPath}`], { cwd: REPO_ROOT });
    try {
      execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "python", containerPath], { cwd: REPO_ROOT });
    } finally {
      try {
        execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "rm", "-f", containerPath], { cwd: REPO_ROOT });
      } catch {
        // Best-effort.
      }
    }
  } finally {
    unlinkSync(tmpFile);
  }
}

async function registerOrgAdmin(page: Page, slugPrefix: string) {
  const slug = unique(slugPrefix).toLowerCase();
  const email = `${slug}@tenant-switcher-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Tenant Switcher E2E Admin");
  await page.getByPlaceholder("Votre email").fill(email);
  await page.getByPlaceholder("Mot de passe (8 caractères min.)").fill(password);
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL("/");

  return { slug, email, password };
}

async function apiHeaders(request: APIRequestContext, email: string, password: string) {
  const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
  if (!loginResponse.ok()) {
    throw new Error(`apiHeaders login(${email}) a échoué (${loginResponse.status()}) : ${await loginResponse.text()}`);
  }
  const { access_token } = await loginResponse.json();
  return { Authorization: `Bearer ${access_token}` };
}

async function meOf(request: APIRequestContext, headers: Record<string, string>) {
  const response = await request.get(`${API_BASE_URL}/api/v1/auth/me`, { headers });
  return response.json();
}

async function organizationOf(request: APIRequestContext, headers: Record<string, string>, organizationId: string) {
  const response = await request.get(`${API_BASE_URL}/api/v1/organizations/${organizationId}`, { headers });
  return response.json();
}

async function schoolsOf(request: APIRequestContext, headers: Record<string, string>, organizationId: string) {
  const response = await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${organizationId}`, { headers });
  return response.json();
}

async function createSecondSchool(request: APIRequestContext, headers: Record<string, string>, organizationId: string, name: string) {
  const slug = unique("second").toLowerCase();
  const response = await request.post(`${API_BASE_URL}/api/v1/schools`, {
    headers,
    data: { organization_id: organizationId, name, slug },
  });
  if (!response.ok()) {
    throw new Error(`createSecondSchool(${slug}) a échoué (${response.status()}) : ${await response.text()}`);
  }
  return response.json();
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

/** Résout l'écran de sélection initiale (organisation puis école, voir AuthGate) jusqu'au tableau
 * de bord — un préalable pour tous les tests ci-dessous, qui portent sur le CHANGEMENT de
 * contexte depuis le sélecteur, pas sur la résolution initiale elle-même. */
async function completeInitialSelection(page: Page, organizationName: string, schoolName: string) {
  await expect(page.getByRole("heading", { name: "Choisissez une organisation" })).toBeVisible();
  await page.getByRole("button", { name: organizationName }).click();
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  await page.getByRole("button", { name: schoolName }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
}

function switcherTrigger(page: Page) {
  return page.getByRole("button", { name: /Contexte actuel/ });
}

/** Un compte SCHOOL_ADMIN + une seconde organisation créée séparément, le même utilisateur
 * recevant ensuite un second rôle SCHOOL_ADMIN scopé à cette organisation (voir
 * assignOrganizationScopedRole) — deux organisations, deux écoles chacune. */
async function setupTwoOrganizationsTwoSchoolsEach(page: Page, request: APIRequestContext, prefix: string) {
  const { email, password } = await registerOrgAdmin(page, `${prefix}A`);
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  const orgAName: string = (await organizationOf(request, headersA, orgAId)).name;
  const orgASchool1 = (await schoolsOf(request, headersA, orgAId))[0];
  const orgASchool2 = await createSecondSchool(request, headersA, orgAId, `Ecole A2 ${unique("x")}`);

  const { email: seedEmail, password: seedPassword } = await registerOrgAdmin(page, `${prefix}B-seed`);
  const headersB = await apiHeaders(request, seedEmail, seedPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await organizationOf(request, headersB, orgBId)).name;
  const orgBSchool1 = (await schoolsOf(request, headersB, orgBId))[0];
  const orgBSchool2 = await createSecondSchool(request, headersB, orgBId, `Ecole B2 ${unique("x")}`);

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  return { email, password, orgAId, orgAName, orgASchool1, orgASchool2, orgBId, orgBName, orgBSchool1, orgBSchool2 };
}

// --- 1, 2, 13 : mono-organisation, plusieurs écoles — badge affiche l'école, sélecteur ouvrable --
test("mono-organisation, plusieurs écoles : badge affiche l'école courante, sélecteur accessible", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "switchmonoorg");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const initialSchools = await schoolsOf(request, headers, organizationId);
  const school1 = initialSchools[0];
  const school2 = await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  await page.getByRole("button", { name: school1.name }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  const trigger = switcherTrigger(page);
  await expect(trigger).toBeVisible();
  await expect(trigger).toContainText(school1.name);
  await expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");

  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("menu", { name: "Changer de contexte" })).toBeVisible();
  // Mono-organisation : aucun groupe "Organisation" n'est proposé, seulement "École".
  await expect(page.getByRole("group", { name: "Organisation" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "École" })).toBeVisible();
  await expect(page.getByRole("menuitemradio", { name: school1.name })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("menuitemradio", { name: school2.name })).toHaveAttribute("aria-checked", "false");

  // Échap ferme le panneau et rend le focus au déclencheur.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

// --- 12 : mono-organisation, mono-école — badge simple, jamais de menu inutile -------------------
test("mono-organisation, mono-école : badge non interactif, aucun menu de changement", async ({ page }) => {
  await registerOrgAdmin(page, "switchmono1x1");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  await expect(switcherTrigger(page)).toHaveCount(0);
  // Le badge reste visible (icône + nom de l'école) mais n'est pas exposé comme un bouton de menu.
  await expect(page.locator("header")).toContainText("🏫");
});

// --- 3, 4, 5, 7, 8, 9, 10, 11, 14 : plusieurs organisations, plusieurs écoles chacune -------------
test("plusieurs organisations : changement d'organisation puis d'école, jamais la première, dashboard recharge, contexte persisté", async ({
  page,
  request,
}) => {
  const setup = await setupTwoOrganizationsTwoSchoolsEach(page, request, "switchmulti");

  await page.evaluate(() => window.localStorage.clear());
  await login(page, setup.email, setup.password);
  await completeInitialSelection(page, setup.orgAName, setup.orgASchool1.name);

  const trigger = switcherTrigger(page);
  await trigger.click();
  await expect(page.getByRole("group", { name: "Organisation" })).toBeVisible();
  await expect(page.getByRole("menuitemradio", { name: setup.orgAName })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("menuitemradio", { name: setup.orgBName })).toHaveAttribute("aria-checked", "false");
  // Jamais un UUID affiché dans le panneau.
  await expect(page.getByText(setup.orgAId)).toHaveCount(0);
  await expect(page.getByText(setup.orgBId)).toHaveCount(0);

  const requestedSchoolUrls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes(`/api/v1/schools/${setup.orgBSchool1.id}`)) requestedSchoolUrls.push(req.url());
  });

  // Choix explicite de l'organisation B — jamais la première (A), jamais implicite.
  await page.getByRole("menuitemradio", { name: setup.orgBName }).click();

  // Le panneau reste ouvert : l'organisation B a plusieurs écoles, le choix suit immédiatement,
  // dans ce même panneau (jamais un rechargement de page complet).
  await expect(page.getByRole("group", { name: "École" })).toBeVisible();
  await expect(page.getByRole("menuitemradio", { name: setup.orgBSchool1.name })).toBeVisible();
  await expect(page.getByRole("menuitemradio", { name: setup.orgBSchool2.name })).toBeVisible();
  // Écoles de l'organisation A jamais mélangées à celles de B (contexte incohérent refusé).
  await expect(page.getByRole("menuitemradio", { name: setup.orgASchool1.name })).toHaveCount(0);
  await expect(page.getByRole("menuitemradio", { name: setup.orgASchool2.name })).toHaveCount(0);

  await page.getByRole("menuitemradio", { name: setup.orgBSchool1.name }).click();
  // Fermé après sélection.
  await expect(page.getByRole("menu")).toHaveCount(0);

  await expect(page.getByText(setup.orgBSchool1.name)).toBeVisible();
  await expect(trigger).toContainText(setup.orgBSchool1.name);
  expect(requestedSchoolUrls.some((url) => url.endsWith(`/schools/${setup.orgBSchool1.id}`))).toBe(true);

  const stored = await page.evaluate(() => window.localStorage.getItem("edulinkage.tenant_context"));
  expect(JSON.parse(stored!)).toMatchObject({ organizationId: setup.orgBId, schoolId: setup.orgBSchool1.id });

  // Persisté au rechargement, sans nouvel écran de sélection.
  await page.reload();
  await expect(page.getByText("Choisissez une organisation")).toHaveCount(0);
  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(switcherTrigger(page)).toContainText(setup.orgBSchool1.name);
});

// --- 6 : organisation choisie avec une seule école -> sélection automatique, sans écran ----------
test("changement vers une organisation à une seule école : sélection automatique, pas d'écran supplémentaire", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "switchautoA");
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  const orgAName: string = (await organizationOf(request, headersA, orgAId)).name;
  const orgASchool1 = (await schoolsOf(request, headersA, orgAId))[0];
  await createSecondSchool(request, headersA, orgAId, `Ecole A2 ${unique("x")}`);

  const { email: seedEmail, password: seedPassword } = await registerOrgAdmin(page, "switchautoB-seed");
  const headersB = await apiHeaders(request, seedEmail, seedPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await organizationOf(request, headersB, orgBId)).name;
  const orgBSchool = (await schoolsOf(request, headersB, orgBId))[0];

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);
  await completeInitialSelection(page, orgAName, orgASchool1.name);

  await switcherTrigger(page).click();
  await page.getByRole("menuitemradio", { name: orgBName }).click();

  // Une seule école dans B : aucun groupe "École" ne doit apparaître, la sélection est automatique.
  await expect(page.getByRole("group", { name: "École" })).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
  // Scopé à <main> : le nom de l'école apparaît aussi, tronqué, dans le bouton du sélecteur lui-même.
  await expect(page.locator("main").getByText(orgBSchool.name)).toBeVisible();

  const stored = await page.evaluate(() => window.localStorage.getItem("edulinkage.tenant_context"));
  expect(JSON.parse(stored!)).toMatchObject({ organizationId: orgBId, schoolId: orgBSchool.id });
});

// --- fermeture au clic extérieur -------------------------------------------------------------------
test("clic à l'extérieur du panneau : ferme le sélecteur sans changer de contexte", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "switchoutside");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const school1 = (await schoolsOf(request, headers, organizationId))[0];
  await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);
  await page.getByRole("button", { name: school1.name }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  await switcherTrigger(page).click();
  await expect(page.getByRole("menu")).toBeVisible();
  // Le panneau est ancré à droite du header (sous le déclencheur) : le logo, tout à gauche, n'est
  // jamais sous son emprise — un clic dessus est un clic extérieur sans ambiguïté de superposition.
  await page.getByText("EduLinkage", { exact: true }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(switcherTrigger(page)).toContainText(school1.name);
});

// --- 15 : logout conserve le comportement actuel --------------------------------------------------
test("déconnexion depuis une session avec sélecteur de contexte : comportement inchangé", async ({ page, request }) => {
  const setup = await setupTwoOrganizationsTwoSchoolsEach(page, request, "switchlogout");

  await page.evaluate(() => window.localStorage.clear());
  await login(page, setup.email, setup.password);
  await completeInitialSelection(page, setup.orgAName, setup.orgASchool1.name);

  await page.getByRole("button", { name: "Déconnexion" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(switcherTrigger(page)).toHaveCount(0);

  // Reconnexion : retrouve normalement le contexte mémorisé (comportement déjà couvert par
  // tenant-context.spec.ts), sans état résiduel du sélecteur.
  await login(page, setup.email, setup.password);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
  await expect(switcherTrigger(page)).toContainText(setup.orgASchool1.name);
});
