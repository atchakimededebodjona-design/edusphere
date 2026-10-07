import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { unlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

// Mise en place des tenants de test. La création d'organisation n'est plus publique : elle passe
// par POST /api/v1/platform/organizations, réservé à un platform admin. Un compte plateforme est
// créé une seule fois par processus de test, directement en base (même mécanisme que
// platform-admin.spec.ts, aucun flux produit ne permet de le créer). Le SCHOOL_ADMIN créé est
// ensuite connecté dans le navigateur via la page /login, comme n'importe quel utilisateur.

export const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
export const TENANT_PASSWORD = "SuperSecret123";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";

let uniqueCounter = 0;
export function unique(prefix: string): string {
  uniqueCounter += 1;
  return `${prefix}${Date.now()}${uniqueCounter}${Math.floor(Math.random() * 10000)}`;
}

function runInApiContainer(script: string): void {
  const tmpFile = path.join(os.tmpdir(), `platform_admin_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  // Copié sous /app (WORKDIR du backend) : `python /chemin.py` n'ajoute que le répertoire du script
  // à sys.path, jamais le cwd — seul /app voit le paquet `app`.
  const containerPath = `/app/platform_admin_e2e_${unique("")}.py`;
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
        // Best-effort : ne jamais masquer une erreur réelle du script pour un échec de nettoyage.
      }
    }
  } finally {
    unlinkSync(tmpFile);
  }
}

export function createPlatformAdminAccount(email: string, password: string): void {
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
}

/** Ajoute un second rôle à un utilisateur EXISTANT, sans toucher à ses rôles actuels — l'API
 * publique (PATCH /users/{id}) REMPLACE le rôle, elle ne peut pas en ajouter un second. Utilisé
 * uniquement pour reproduire un compte mixte (ex. SCHOOL_ADMIN + TEACHER) en test, un état que le
 * produit ne permet pas de créer via son propre flux — même motif que createPlatformAdminAccount. */
export function assignExtraRole(
  userId: string,
  roleCode: string,
  organizationId: string,
  schoolId: string | null,
): void {
  const script = [
    "import asyncio, uuid",
    "from sqlalchemy import select",
    "from app.db import model_registry  # noqa: F401",
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
    `            school_id=${schoolId ? `uuid.UUID(${JSON.stringify(schoolId)})` : "None"},`,
    "        ))",
    "        await db.commit()",
    "",
    "asyncio.run(main())",
  ].join("\n");
  runInApiContainer(script);
}

let platformAdminEmail: string | null = null;

async function loginApi(request: APIRequestContext, email: string, password: string): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
  if (!response.ok()) {
    throw new Error(`login API (${email}) a échoué (${response.status()}) : ${await response.text()}`);
  }
  const { access_token } = await response.json();
  return access_token;
}

async function platformAdminHeaders(request: APIRequestContext): Promise<Record<string, string>> {
  if (platformAdminEmail === null) {
    const email = `${unique("platformtenants").toLowerCase()}@platform-e2e.example`;
    createPlatformAdminAccount(email, TENANT_PASSWORD);
    platformAdminEmail = email;
  }
  const token = await loginApi(request, platformAdminEmail, TENANT_PASSWORD);
  return { Authorization: `Bearer ${token}` };
}

export type TenantAdmin = {
  slug: string;
  orgId: string;
  schoolId: string;
  orgAdminEmail: string;
  password: string;
  orgAdminToken: string;
};

/** Crée organisation + école principale + SCHOOL_ADMIN via POST /api/v1/platform/organizations,
 * puis obtient le token du SCHOOL_ADMIN créé (sans toucher au navigateur). */
export async function createOrganizationViaPlatform(request: APIRequestContext, slugPrefix: string): Promise<TenantAdmin> {
  const slug = unique(slugPrefix).toLowerCase();
  const orgAdminEmail = `${slug}-org@wizard-e2e.example`;
  const headers = await platformAdminHeaders(request);

  const response = await request.post(`${API_BASE_URL}/api/v1/platform/organizations`, {
    headers,
    data: {
      organization: { name: `Org ${slug}`, slug, country_code: "TG" },
      school: { name: `Ecole ${slug}`, slug },
      admin: { full_name: "Org Admin", email: orgAdminEmail, password: TENANT_PASSWORD },
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  const created = await response.json();

  const orgAdminToken = await loginApi(request, orgAdminEmail, TENANT_PASSWORD);
  return {
    slug,
    orgId: created.organization.id,
    schoolId: created.school.id,
    orgAdminEmail,
    password: TENANT_PASSWORD,
    orgAdminToken,
  };
}

/** Vide le compteur de `reset-password` (rate limit par IP, partagé par toutes les requêtes de la
 * suite e2e). Même motif que le nettoyage Redis de l'ancien rate limit d'inscription : on nettoie
 * l'état de test, jamais le seuil applicatif. Best-effort : Redis indisponible ne fait pas échouer. */
export function clearResetPasswordRateLimit(): void {
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
        "redis-cli --scan --pattern 'reset_password_attempts:*' | xargs -r redis-cli del",
      ],
      { cwd: REPO_ROOT },
    );
  } catch {
    // Best-effort : le rate limiting fail-open côté backend reste la garantie réelle.
  }
}

/** Connexion réelle dans le navigateur via la page /login (seul point d'entrée des utilisateurs). */
export async function loginInBrowser(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");
}

/** Raccourci : crée le tenant via l'API puis ouvre une session navigateur pour son SCHOOL_ADMIN. */
export async function registerOrgAdminInBrowser(page: Page, slugPrefix: string): Promise<TenantAdmin> {
  const tenant = await createOrganizationViaPlatform(page.context().request, slugPrefix);
  await loginInBrowser(page, tenant.orgAdminEmail, tenant.password);
  return tenant;
}

/** Headers d'un compte plateforme partagé, pour les specs qui appellent l'API directement. */
export { platformAdminHeaders };
