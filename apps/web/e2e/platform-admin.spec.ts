import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext } from "@playwright/test";

// Correction du flux super administrateur plateforme — un compte is_platform_admin=true n'a
// structurellement aucune organisation/école (voir lib/auth/roles.ts::isPlatformAdmin,
// app/(app)/AuthGate.tsx). Ce produit n'a pas de flux self-service pour créer ce type de compte
// (seed uniquement, voir apps/api/tests/conftest.py::create_platform_admin côté backend) — reproduit
// ici directement en base via `docker compose exec`, même mécanisme déjà établi par
// tenant-context.spec.ts::assignOrganizationScopedRole pour les états hors des flux produit normaux.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";
const PLATFORM_ADMIN_PASSWORD = "SuperSecret123";

let uniqueCounter = 0;
function unique(prefix: string): string {
  uniqueCounter += 1;
  return `${prefix}${Date.now()}${uniqueCounter}${Math.floor(Math.random() * 10000)}`;
}

function runInApiContainer(script: string): void {
  const tmpFile = path.join(os.tmpdir(), `platform_admin_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  // Copié sous /app (WORKDIR du backend, voir apps/api/Dockerfile) : `python /chemin.py` ajoute le
  // répertoire du script à sys.path, jamais le cwd — seul /app/... voit le paquet `app`.
  const containerScriptName = `platform_admin_e2e_${unique("")}.py`;
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

/** Crée un compte plateforme pur (is_platform_admin=true, rôle SUPER_ADMIN, aucune organisation ni
 * école) directement en base — aucun flux produit ne permet de créer ce type de compte (comportement
 * intentionnel, voir apps/api/tests/test_auth.py::test_register_never_grants_platform_admin). */
function createPlatformAdminAccount(email: string, password: string): string {
  const userId = randomUUID();
  const script = [
    "import asyncio, uuid",
    "from sqlalchemy import select",
    "from app.db import model_registry  # noqa: F401 -- enregistre tous les modèles ORM (FK)",
    "from app.core.security import hash_password",
    "from app.core.tenancy import set_platform_wide_context",
    "from app.db.session import AsyncSessionLocal",
    "from app.modules.rbac.models import Role, UserRole",
    "from app.modules.users.models import User",
    "",
    "async def main():",
    "    async with AsyncSessionLocal() as db:",
    "        await set_platform_wide_context(db)",
    "        db.add(User(",
    `            id=uuid.UUID(${JSON.stringify(userId)}),`,
    `            email=${JSON.stringify(email)},`,
    '            full_name="Platform Admin E2E",',
    `            hashed_password=hash_password(${JSON.stringify(password)}),`,
    "            is_active=True,",
    "            is_platform_admin=True,",
    "        ))",
    "        await db.flush()",
    '        role = (await db.execute(select(Role).where(Role.code == "SUPER_ADMIN"))).scalar_one()',
    "        db.add(UserRole(",
    "            id=uuid.uuid4(),",
    `            user_id=uuid.UUID(${JSON.stringify(userId)}),`,
    "            role_id=role.id,",
    "            organization_id=None,",
    "            school_id=None,",
    "        ))",
    "        await db.commit()",
    "",
    "asyncio.run(main())",
  ].join("\n");
  runInApiContainer(script);
  return userId;
}

async function apiHeaders(request: APIRequestContext, email: string, password: string) {
  const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
  if (!loginResponse.ok()) {
    throw new Error(`apiHeaders login(${email}) a échoué (${loginResponse.status()}) : ${await loginResponse.text()}`);
  }
  const { access_token } = await loginResponse.json();
  return { Authorization: `Bearer ${access_token}` };
}

test("super administrateur plateforme (0 organisation, 0 école) : accède au tableau de bord plateforme, jamais bloqué", async ({
  page,
  request,
}) => {
  const email = `${unique("platformadmin").toLowerCase()}@platform-e2e.example`;
  createPlatformAdminAccount(email, PLATFORM_ADMIN_PASSWORD);

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(PLATFORM_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();

  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByText("Aucune organisation ou école accessible avec ce compte.")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Administration de la plateforme" })).toBeVisible();
  await expect(page.getByText("Bienvenue dans l'espace d'administration EduLinkage.")).toBeVisible();

  // Compte fraîchement créé, zéro organisation/école préexistante attribuée à cet utilisateur :
  // les métriques réelles (pas de placeholder, jamais de donnée inventée) restent affichables même
  // à zéro — jamais un écran de chargement infini ni une erreur.
  await expect(page.getByText("Chargement des indicateurs...")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByText("Organisations")).toBeVisible();
  await expect(page.getByText("Écoles")).toBeVisible();
  await expect(page.getByText("Utilisateurs")).toBeVisible();
  await expect(page.getByText("Élèves")).toBeVisible();
});

test("GET /platform/dashboard : accessible à un compte plateforme, refusé à un compte non-plateforme", async ({
  request,
}) => {
  const platformEmail = `${unique("platformapi").toLowerCase()}@platform-e2e.example`;
  createPlatformAdminAccount(platformEmail, PLATFORM_ADMIN_PASSWORD);
  const platformHeaders = await apiHeaders(request, platformEmail, PLATFORM_ADMIN_PASSWORD);

  const platformResponse = await request.get(`${API_BASE_URL}/api/v1/platform/dashboard`, { headers: platformHeaders });
  expect(platformResponse.ok()).toBe(true);
  const body = await platformResponse.json();
  expect(typeof body.organization_count).toBe("number");
  expect(typeof body.school_count).toBe("number");
  expect(typeof body.user_count).toBe("number");
  expect(typeof body.student_count).toBe("number");

  const registerResponse = await request.post(`${API_BASE_URL}/api/v1/auth/register`, {
    data: {
      organization_name: "Not Platform Org",
      organization_slug: unique("notplatform").toLowerCase(),
      country_code: "TG",
      school_name: "Not Platform School",
      school_slug: "principale",
      admin_full_name: "Not Platform Admin",
      admin_email: `${unique("notplatform").toLowerCase()}@platform-e2e.example`,
      admin_password: "SuperSecret123",
    },
  });
  const registered = await registerResponse.json();
  const schoolAdminHeaders = { Authorization: `Bearer ${registered.tokens.access_token}` };

  const forbiddenResponse = await request.get(`${API_BASE_URL}/api/v1/platform/dashboard`, {
    headers: schoolAdminHeaders,
  });
  expect(forbiddenResponse.status()).toBe(403);
});
