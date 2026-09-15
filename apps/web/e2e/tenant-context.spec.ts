import { execFileSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Sélection multi-organisation/multi-école (correctif du choix arbitraire du premier rôle
// scopé organisation, voir lib/auth/AuthProvider.tsx + lib/auth/tenantContext.ts). Ce projet n'a
// pas de runner de test unitaire JS (voir auth-session-resilience.spec.ts) : ces scénarios sont
// donc couverts ici en E2E réel, contre l'API + Postgres (docker compose), même convention.
//
// Un compte réellement rattaché à DEUX organisations (le bug rapporté) n'est atteignable par
// AUCUN flux produit légitime : `POST /auth/register` crée toujours un NOUVEL utilisateur (email
// unique, 409 sur un email déjà pris) et `POST /users` ne peut attribuer qu'un rôle scopé à une
// école de l'organisation de l'appelant, jamais un second rôle scopé organisation pour une AUTRE
// organisation. C'est exactement l'état de données rapporté (anomalie historique, pas un parcours
// que le produit permet de créer) — `assignOrganizationScopedRole` ci-dessous le reproduit par le
// même mécanisme que le fait déjà `apps/api/tests/conftest.py::assign_role` côté backend (écriture
// directe, contexte tenant élargi explicitement), invoqué ici via `docker compose exec`, jamais
// via une dépendance npm nouvelle.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
// Nom de projet Compose explicite (`docker compose ls`) : nécessaire quand ces commandes sont
// invoquées depuis un point de montage dont le nom de dossier diffère de celui du dépôt (ex. un
// conteneur qui monte le dépôt sous /repo) — Compose dérive sinon le nom de projet du dossier
// courant et manquerait les services déjà démarrés sous le vrai nom du projet.
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";

// Compteur monotone en plus de Date.now()/random : plusieurs organisations/écoles sont créées par
// un même test (et par plusieurs tests en parallèle, `fullyParallel: true`), suffisamment vite
// pour que deux appels retombent sur le même milliseconde + tirage aléatoire (slug alors en
// collision, 409 silencieux si non vérifié) — un compteur exclut cette collision par construction.
let uniqueCounter = 0;
function unique(prefix: string): string {
  uniqueCounter += 1;
  return `${prefix}${Date.now()}${uniqueCounter}${Math.floor(Math.random() * 10000)}`;
}

// Ce fichier enregistre plusieurs comptes par test (organisation "de départ" + une seconde
// organisation jetable pour simuler le cas multi-organisation) — largement plus que la suite e2e
// existante qui avait déjà motivé le seuil actuel de /auth/register (20/heure par IP, voir
// docs/deployment/PRODUCTION_CONFIGURATION.md "Phase 20" : toutes les requêtes Playwright
// partagent la même IP apparente). Vidé avant CHAQUE test, même motif que
// apps/api/tests/conftest.py::_clear_register_rate_limit côté backend — jamais une modification
// du seuil applicatif lui-même, seulement un nettoyage de l'état de test.
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
    // Best-effort : si Redis est momentanément indisponible, le rate limiting fail-open déjà en
    // place côté backend (voir app/core/rate_limit.py) reste la garantie réelle, pas ce nettoyage.
  }
}

test.beforeEach(() => {
  clearRegisterRateLimit();
});

/** Attribue directement un rôle scopé organisation (ou plateforme, si `organizationId` est
 * `null`) à un utilisateur déjà existant — reproduit un état que le produit ne permet pas de
 * créer par lui-même (voir commentaire d'en-tête). Jamais utilisé pour un rôle scopé école : ce
 * cas est déjà entièrement atteignable via `POST /users`, voir les autres helpers ci-dessous. */
function assignOrganizationScopedRole(
  userId: string,
  roleCode: string,
  organizationId: string | null,
): void {
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
    organizationId ? `            organization_id=uuid.UUID(${JSON.stringify(organizationId)}),` : "            organization_id=None,",
    "            school_id=None,",
    "        ))",
    "        await db.commit()",
    "",
    "asyncio.run(main())",
  ].join("\n");

  const tmpFile = path.join(os.tmpdir(), `assign_role_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  // Copié sous /app (pas /tmp) : `python /chemin/absolu.py` ajoute le RÉPERTOIRE DU SCRIPT à
  // sys.path (jamais le cwd) — seul /app/... voit le paquet `app` du backend (WORKDIR /app,
  // voir apps/api/Dockerfile). Nom de fichier unique pour ne jamais entrer en collision si
  // plusieurs tests l'invoquent en séquence.
  const containerScriptName = `assign_role_e2e_${unique("")}.py`;
  const containerPath = `/app/${containerScriptName}`;
  try {
    execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "cp", tmpFile, `api:${containerPath}`], {
      cwd: REPO_ROOT,
    });
    try {
      execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "python", containerPath], {
        cwd: REPO_ROOT,
      });
    } finally {
      try {
        execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "rm", "-f", containerPath], {
          cwd: REPO_ROOT,
        });
      } catch {
        // Best-effort : ne jamais masquer une erreur réelle du script ci-dessus pour un simple
        // échec de nettoyage.
      }
    }
  } finally {
    unlinkSync(tmpFile);
  }
}

/** Supprime tous les rôles existants d'un utilisateur — utilisé uniquement pour reproduire un
 * compte réduit à un unique rôle plateforme (scénario 11) : `registerOrgAdmin` crée toujours un
 * rôle SCHOOL_ADMIN scopé organisation, qu'`assignOrganizationScopedRole` seul ne retire pas
 * (purement additif). Aucun flux produit ne retire non plus le dernier rôle d'un compte ; reproduit
 * ici directement, même mécanisme que ci-dessus. */
function removeAllRolesForUser(userId: string): void {
  const script = [
    "import asyncio, uuid",
    "from sqlalchemy import delete",
    "from app.db import model_registry  # noqa: F401 -- enregistre tous les modèles ORM (FK)",
    "from app.core.tenancy import set_platform_wide_context",
    "from app.db.session import AsyncSessionLocal",
    "from app.modules.rbac.models import UserRole",
    "",
    "async def main():",
    "    async with AsyncSessionLocal() as db:",
    "        await set_platform_wide_context(db)",
    `        await db.execute(delete(UserRole).where(UserRole.user_id == uuid.UUID(${JSON.stringify(userId)})))`,
    "        await db.commit()",
    "",
    "asyncio.run(main())",
  ].join("\n");

  const tmpFile = path.join(os.tmpdir(), `remove_roles_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerScriptName = `remove_roles_e2e_${unique("")}.py`;
  const containerPath = `/app/${containerScriptName}`;
  try {
    execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "cp", tmpFile, `api:${containerPath}`], {
      cwd: REPO_ROOT,
    });
    try {
      execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "python", containerPath], {
        cwd: REPO_ROOT,
      });
    } finally {
      try {
        execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "rm", "-f", containerPath], {
          cwd: REPO_ROOT,
        });
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
  const email = `${slug}@tenant-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Tenant E2E Admin");
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

function readSession(page: Page, key: string) {
  return page.evaluate((k) => window.localStorage.getItem(k), key);
}

// --- 1 : une organisation + une seule école -> resolved automatiquement ------------------------
test("1 organisation, 1 école : résolution automatique, aucun écran de sélection", async ({ page }) => {
  await registerOrgAdmin(page, "singleorg1school");
  await expect(page.getByText("Choisissez une organisation")).toHaveCount(0);
  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 2 : une organisation + plusieurs écoles -> sélection d'école -------------------------------
test("1 organisation, plusieurs écoles : sélection d'école explicite, jamais arbitraire", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "singleorgmultischool");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const secondSchool = await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);

  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  await expect(page.getByText("Choisissez une organisation")).toHaveCount(0);
  await expect(page.getByRole("button", { name: secondSchool.name })).toBeVisible();

  await page.getByRole("button", { name: secondSchool.name }).click();
  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 3 : plusieurs organisations, une école chacune -> sélection d'organisation -----------------
test("plusieurs organisations (1 école chacune) : sélection d'organisation explicite, jamais la première", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "multiorgA");
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  const orgAName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgAId}`, { headers: headersA })).json()).name;

  // Deuxième organisation, créée séparément (compte jetable), puis le MÊME utilisateur y reçoit un
  // second rôle SCHOOL_ADMIN scopé organisation — état que le produit ne permet pas de créer
  // lui-même (voir commentaire d'en-tête).
  const { email: throwawayEmail, password: throwawayPassword } = await registerOrgAdmin(page, "multiorgB-seed");
  const headersB = await apiHeaders(request, throwawayEmail, throwawayPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgBId}`, { headers: headersB })).json()).name;

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);

  await expect(page.getByRole("heading", { name: "Choisissez une organisation" })).toBeVisible();
  await expect(page.getByRole("button", { name: orgAName })).toBeVisible();
  await expect(page.getByRole("button", { name: orgBName })).toBeVisible();
  // Jamais un UUID ni un slug affiché.
  await expect(page.getByText(orgAId)).toHaveCount(0);
  await expect(page.getByText(orgBId)).toHaveCount(0);

  await page.getByRole("button", { name: orgBName }).click();
  await expect(page.getByText("Choisissez une organisation")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 4 : plusieurs organisations, plusieurs écoles -> organisation puis école -------------------
test("plusieurs organisations, plusieurs écoles chacune : organisation puis école, dans cet ordre", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "multiorgmultischoolA");
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  await createSecondSchool(request, headersA, orgAId, `Ecole A2 ${unique("x")}`);

  const { email: throwawayEmail, password: throwawayPassword } = await registerOrgAdmin(page, "multiorgmultischoolB-seed");
  const headersB = await apiHeaders(request, throwawayEmail, throwawayPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgBId}`, { headers: headersB })).json()).name;
  const secondSchoolB = await createSecondSchool(request, headersB, orgBId, `Ecole B2 ${unique("x")}`);

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);

  await expect(page.getByRole("heading", { name: "Choisissez une organisation" })).toBeVisible();
  await page.getByRole("button", { name: orgBName }).click();

  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  await expect(page.getByRole("button", { name: secondSchoolB.name })).toBeVisible();
  await page.getByRole("button", { name: secondSchoolB.name }).click();

  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 5 : contexte localStorage valide -> restauré -----------------------------------------------
test("contexte localStorage valide (nouvelle clé) : restauré sans nouvel écran de sélection", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "storagevalid");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  const schools = await (await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${organizationId}`, { headers })).json();
  await page.getByRole("button", { name: schools[0].name }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  const stored = await readSession(page, "edulinkage.tenant_context");
  expect(stored).toBeTruthy();
  expect(JSON.parse(stored!)).toMatchObject({ organizationId, schoolId: schools[0].id });

  await page.reload();
  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 6 : contexte localStorage invalide -> ignoré et sélection demandée -------------------------
test("contexte localStorage invalide (école inexistante) : ignoré, sélection redemandée", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "storageinvalid");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.goto("/login");
  await page.evaluate(
    ({ organizationId: orgId }) => {
      window.localStorage.setItem(
        "edulinkage.tenant_context",
        JSON.stringify({ organizationId: orgId, schoolId: "00000000-0000-0000-0000-000000000000" }),
      );
    },
    { organizationId },
  );
  await login(page, email, password);

  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
});

// --- 7 : schoolId appartenant à une autre organisation -> refusé, nouvelle sélection ------------
test("schoolId mémorisé appartenant à une autre organisation : jamais réutilisé, nouvelle sélection demandée", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "crossorgstale");
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  const orgASchoolId: string = (await (await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${orgAId}`, { headers: headersA })).json())[0].id;

  const { email: throwawayEmail, password: throwawayPassword } = await registerOrgAdmin(page, "crossorgstale-seed");
  const headersB = await apiHeaders(request, throwawayEmail, throwawayPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgBId}`, { headers: headersB })).json()).name;
  await createSecondSchool(request, headersB, orgBId, `Ecole B2 ${unique("x")}`);

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  await page.goto("/login");
  // Contexte mémorisé pointant vers l'organisation B mais avec le schoolId de l'organisation A
  // (ex. reliquat d'un état antérieur incohérent) : ne doit jamais être accepté tel quel pour B.
  await page.evaluate(
    ({ organizationId, schoolId }) => {
      window.localStorage.setItem("edulinkage.tenant_context", JSON.stringify({ organizationId, schoolId }));
    },
    { organizationId: orgBId, schoolId: orgASchoolId },
  );
  await login(page, email, password);

  await expect(page.getByRole("heading", { name: "Choisissez une organisation" })).toBeVisible();
  await page.getByRole("button", { name: orgBName }).click();
  // École de A jamais proposée ni acceptée pour B : sélection d'école redemandée normalement.
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
});

// --- 8/9 : anciennes clés -> migration douce si compatible --------------------------------------
test("ancienne clé edulinkage.selected_school_id compatible : migrée, sélection restaurée", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "legacynew");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const secondSchool = await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.goto("/login");
  // `registerOrgAdmin` a déjà connecté ce compte une première fois quand l'organisation n'avait
  // qu'une seule école : la nouvelle clé `edulinkage.tenant_context` a alors été écrite (résolution
  // automatique) — jamais nettoyée, elle serait sinon considérée valide et prioritaire, empêchant
  // toute migration depuis l'ancienne clé posée ci-dessous d'être même consultée.
  await page.evaluate(() => window.localStorage.clear());
  await page.evaluate((schoolId) => window.localStorage.setItem("edulinkage.selected_school_id", schoolId), secondSchool.id);
  await login(page, email, password);

  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  const migrated = await readSession(page, "edulinkage.tenant_context");
  expect(JSON.parse(migrated!)).toMatchObject({ organizationId, schoolId: secondSchool.id });
  const legacyAfter = await readSession(page, "edulinkage.selected_school_id");
  expect(legacyAfter).toBeNull();
});

test("ancienne clé edusphere.selected_school_id compatible : migrée, sélection restaurée", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "legacyold");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const secondSchool = await createSecondSchool(request, headers, organizationId, `Ecole B ${unique("x")}`);

  await page.goto("/login");
  // Même motif que le test précédent : nettoyer la nouvelle clé déjà écrite lors de l'inscription
  // (organisation à une seule école à ce moment-là) avant de poser l'ancienne clé à migrer.
  await page.evaluate(() => window.localStorage.clear());
  await page.evaluate((schoolId) => window.localStorage.setItem("edusphere.selected_school_id", schoolId), secondSchool.id);
  await login(page, email, password);

  await expect(page.getByText("Choisissez une école")).toHaveCount(0);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  const migrated = await readSession(page, "edulinkage.tenant_context");
  expect(JSON.parse(migrated!)).toMatchObject({ organizationId, schoolId: secondSchool.id });
  const legacyAfter = await readSession(page, "edusphere.selected_school_id");
  expect(legacyAfter).toBeNull();
});

// --- 10 : utilisateur sans organisation -> empty --------------------------------------------------
// --- 11 : rôle plateforme sans organisation ni école -> comportement actuel conservé / empty -----
test("rôle plateforme (sans organisation ni école) : aucun contexte, message clair, pas de blocage", async ({ page, request }) => {
  const { email, password } = await registerOrgAdmin(page, "platformonly-seed");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const userId: string = me.user.id;

  // Compte réduit à un unique rôle plateforme (organization_id ET school_id NULL) : ce produit
  // n'a pas de flux self-service pour créer ce genre de compte non plus (même justification que
  // le scénario multi-organisation ci-dessus) — reproduit directement. Le rôle SCHOOL_ADMIN créé
  // par `registerOrgAdmin` est retiré au préalable : `assignOrganizationScopedRole` est purement
  // additif et ne le retirerait pas lui-même.
  removeAllRolesForUser(userId);
  assignOrganizationScopedRole(userId, "PLATFORM_SUPPORT", null);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);

  await expect(page.getByText("Aucune organisation ou école accessible avec ce compte.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
});

// --- 12 : aucun choix arbitraire basé sur roles[0] ------------------------------------------------
// Déjà démontré structurellement par les scénarios 3/4/7 ci-dessus (l'organisation B, ajoutée
// APRÈS l'organisation A dans `roles`, est proposée et peut être choisie — jamais l'organisation A
// choisie automatiquement au seul motif qu'elle apparaît en premier).

// --- 13 : changement d'organisation -> contexte école réinitialisé/revalidé ----------------------
test("changement d'organisation : le contexte école précédent est réinitialisé, jamais réutilisé pour la nouvelle organisation", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "switchorgA");
  const headersA = await apiHeaders(request, email, password);
  const meA = await meOf(request, headersA);
  const userId: string = meA.user.id;
  const orgAId: string = meA.roles[0].organization_id;
  const orgASchool = (await (await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${orgAId}`, { headers: headersA })).json())[0];

  const { email: throwawayEmail, password: throwawayPassword } = await registerOrgAdmin(page, "switchorgB-seed");
  const headersB = await apiHeaders(request, throwawayEmail, throwawayPassword);
  const meB = await meOf(request, headersB);
  const orgBId: string = meB.roles[0].organization_id;
  const orgBName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgBId}`, { headers: headersB })).json()).name;
  const orgBSchool = (await (await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${orgBId}`, { headers: headersB })).json())[0];

  assignOrganizationScopedRole(userId, "SCHOOL_ADMIN", orgBId);

  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);

  const orgAName: string = (await (await request.get(`${API_BASE_URL}/api/v1/organizations/${orgAId}`, { headers: headersA })).json()).name;
  await page.getByRole("button", { name: orgAName }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
  const afterA = await readSession(page, "edulinkage.tenant_context");
  expect(JSON.parse(afterA!)).toMatchObject({ organizationId: orgAId, schoolId: orgASchool.id });

  // Reconnexion, choix de l'AUTRE organisation cette fois.
  await page.evaluate(() => window.localStorage.clear());
  await login(page, email, password);
  await page.getByRole("button", { name: orgBName }).click();
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  const afterB = await readSession(page, "edulinkage.tenant_context");
  const parsedAfterB = JSON.parse(afterB!);
  expect(parsedAfterB.organizationId).toBe(orgBId);
  expect(parsedAfterB.schoolId).toBe(orgBSchool.id);
  expect(parsedAfterB.schoolId).not.toBe(orgASchool.id);
});

// --- 14 : logout -> contexte tenant nettoyé (état React, pas la mémorisation navigateur) --------
test("logout : le contexte tenant en mémoire est nettoyé, un état de chargement propre suit une reconnexion", async ({
  page,
}) => {
  const { email, password } = await registerOrgAdmin(page, "logoutclean");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();

  await page.getByRole("button", { name: "Déconnexion" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // Reconnexion : la résolution repart proprement (pas d'état "bloqué" hérité de la session
  // précédente), et retrouve le même contexte (mémorisation navigateur toujours présente, comme
  // attendu — voir scénario 5).
  await login(page, email, password);
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

// --- 15 : régression dashboard -> getSchool()/getSchoolDashboard() reçoivent bien currentSchoolId -
test("régression dashboard : getSchool()/getSchoolDashboard() sont bien appelés avec le school_id résolu", async ({
  page,
  request,
}) => {
  const { email, password } = await registerOrgAdmin(page, "dashregression");
  const headers = await apiHeaders(request, email, password);
  const me = await meOf(request, headers);
  const organizationId: string = me.roles[0].organization_id;
  const school = (await (await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${organizationId}`, { headers })).json())[0];

  const calledSchoolUrls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes(`/api/v1/schools/${school.id}`)) calledSchoolUrls.push(req.url());
  });

  await page.goto("/");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
  await expect(page.getByText("Chargement des indicateurs...")).toHaveCount(0, { timeout: 10_000 });

  expect(calledSchoolUrls.some((url) => url.endsWith(`/schools/${school.id}`))).toBe(true);
  expect(calledSchoolUrls.some((url) => url.endsWith(`/schools/${school.id}/dashboard`))).toBe(true);
});
