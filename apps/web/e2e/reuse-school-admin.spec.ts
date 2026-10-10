import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// PR #20 — un même compte administrateur pour plusieurs écoles d'UNE organisation, dans le
// navigateur :
// 1. Platform Owner : Collège avec un nouvel admin (Wade), puis Lycée en « administrateur existant »
//    (email seul, aucun mot de passe demandé) => compte réutilisé ;
// 2. Wade se connecte UNE fois (mot de passe d'origine) et choisit entre ses deux écoles ;
// 3. l'email d'un admin d'une AUTRE organisation est refusé, aucune école créée ;
// 4. Partenaire : réutilisation scopée + admin org-wide qui couvre déjà la nouvelle école.
const API = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";
// Conteneur API isolé optionnel (voir platform-student-aggregates.spec.ts).
const API_CONTAINER = process.env.PLAYWRIGHT_API_CONTAINER;
const PASSWORD = "SuperSecret123";

test.describe.configure({ mode: "serial" });

let counter = 0;
function unique(prefix: string): string {
  counter += 1;
  return `${prefix}${Date.now()}${counter}${Math.floor(Math.random() * 10000)}`;
}

function runInApiContainer(script: string): void {
  if (API_CONTAINER) {
    execFileSync("docker", ["exec", "-i", "-w", "/app", API_CONTAINER, "python", "-"], { input: script });
    return;
  }
  const tmpFile = path.join(os.tmpdir(), `reuse_admin_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerPath = `/app/reuse_admin_e2e_${unique("")}.py`;
  try {
    execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "cp", tmpFile, `api:${containerPath}`], { cwd: REPO_ROOT });
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

function createPlatformOwner(email: string): void {
  const userId = randomUUID();
  runInApiContainer(
    [
      "import asyncio, uuid",
      "from sqlalchemy import select",
      "from app.db import model_registry  # noqa: F401",
      "from app.core.security import hash_password",
      "from app.core.tenancy import set_platform_wide_context",
      "from app.db.session import AsyncSessionLocal",
      "from app.modules.rbac.models import Role, UserRole",
      "from app.modules.users.models import User",
      "",
      "async def main():",
      "    async with AsyncSessionLocal() as db:",
      "        await set_platform_wide_context(db)",
      `        db.add(User(id=uuid.UUID(${JSON.stringify(userId)}), email=${JSON.stringify(email)},`,
      `            full_name="Owner Reuse E2E", hashed_password=hash_password(${JSON.stringify(PASSWORD)}),`,
      "            is_active=True, is_platform_admin=True))",
      "        await db.flush()",
      '        role = (await db.execute(select(Role).where(Role.code == "PLATFORM_OWNER"))).scalar_one()',
      `        db.add(UserRole(id=uuid.uuid4(), user_id=uuid.UUID(${JSON.stringify(userId)}), role_id=role.id,`,
      "            organization_id=None, school_id=None))",
      "        await db.commit()",
      "",
      "asyncio.run(main())",
    ].join("\n"),
  );
}

async function token(request: APIRequestContext, email: string, password = PASSWORD): Promise<string> {
  const response = await request.post(`${API}/api/v1/auth/login`, { data: { email, password } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function loginUi(page: Page, email: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => window.localStorage.clear());
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

function orgPayload(name: string, adminEmail: string) {
  return {
    organization: { name, slug: unique("org").toLowerCase(), country_code: "TG" },
    school: { name: "Complexe scolaire EDULINKAGE", slug: "principale" },
    admin: { full_name: "Admin Complexe", email: adminEmail, password: PASSWORD },
  };
}

async function openOrganization(page: Page, orgName: string) {
  await page.goto("/dashboard/organizations/new?mode=existing");
  await page.getByLabel("Rechercher une organisation existante").fill(orgName);
  await page.getByRole("button", { name: "Rechercher" }).click();
  const results = page.getByRole("list", { name: "Organisations trouvées" }).getByRole("button");
  await expect(results).toHaveCount(1);
  await results.first().click();
  return page.getByRole("region", { name: "Organisation sélectionnée" });
}

async function addSchool(page: Page, schoolName: string, email: string, existing: boolean) {
  await page.getByLabel("Nom du nouvel établissement").fill(schoolName);
  const checkbox = page.getByRole("checkbox", { name: /L'administrateur possède déjà un compte/ });
  if (existing) {
    await checkbox.check();
    // Aucun champ mot de passe ni nom : rien à saisir pour un compte existant.
    await expect(page.getByLabel("Mot de passe initial de l'administrateur")).toHaveCount(0);
    await expect(page.getByLabel("Nom de l'administrateur")).toHaveCount(0);
  } else {
    await checkbox.uncheck();
    await page.getByLabel("Nom de l'administrateur").fill("Wade");
    await page.getByLabel("Mot de passe initial de l'administrateur").fill(PASSWORD);
    await page.getByLabel("Confirmation du mot de passe de l'administrateur").fill(PASSWORD);
  }
  await page.getByLabel("Email de l'administrateur").fill(email);
  await page.getByRole("button", { name: "Ajouter l'établissement" }).click();
}

test("Platform Owner : un même administrateur (Wade) pour le Collège et le Lycée, connexion unique, refus inter-organisation", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("r20owner").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const ownerToken = await token(request, ownerEmail);
  const orgName = `EduLinkage Togo Pilote ${unique("")}`;
  const created = await request.post(`${API}/api/v1/platform/organizations`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: orgPayload(orgName, `${unique("complexe").toLowerCase()}@platform-e2e.example`),
  });
  expect(created.status(), await created.text()).toBe(201);
  const otherOrg = await request.post(`${API}/api/v1/platform/organizations`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: orgPayload(`Autre Organisation ${unique("")}`, `${unique("autre").toLowerCase()}@platform-e2e.example`),
  });
  const otherAdminEmail = (await otherOrg.json()).admin.email as string;
  const wade = `${unique("wade").toLowerCase()}@platform-e2e.example`;

  // 1. Collège avec un NOUVEL admin (Wade), puis Lycée en réutilisant son compte.
  await loginUi(page, ownerEmail);
  await expect(page).toHaveURL("/dashboard");
  const selected = await openOrganization(page, orgName);
  await addSchool(page, "Collège EduLinkage", wade, false);
  await expect(page.getByText(/Établissement « Collège EduLinkage » ajouté à .* Son administrateur peut se connecter\./)).toBeVisible();
  await addSchool(page, "Lycée EduLinkage", wade, true);
  await expect(
    page.getByText(`Compte administrateur existant réutilisé : ${wade} administre désormais aussi cet établissement (mot de passe inchangé).`, {
      exact: false,
    }),
  ).toBeVisible();
  await expect(selected.getByRole("list", { name: "Établissements existants" }).getByRole("listitem")).toHaveText([
    "✓ Complexe scolaire EDULINKAGE",
    "✓ Collège EduLinkage",
    "✓ Lycée EduLinkage",
  ]);

  // 3. Email d'un admin d'une AUTRE organisation : refus générique, aucune école créée.
  await addSchool(page, "Annexe EduLinkage", otherAdminEmail, true);
  await expect(page.getByText("cet email ne peut pas être utilisé pour administrer cet établissement", { exact: false })).toBeVisible();
  await expect(selected.getByRole("list", { name: "Établissements existants" }).getByRole("listitem")).toHaveCount(3);

  // 2. Wade : un seul compte, une seule connexion (mot de passe d'origine), choix entre SES 2 écoles.
  const wadeToken = await token(request, wade);
  const me = await request.get(`${API}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${wadeToken}` } });
  const roles = (await me.json()).roles as Array<{ role_code: string; school_id: string | null }>;
  expect(roles.map((r) => r.role_code)).toEqual(["SCHOOL_ADMIN", "SCHOOL_ADMIN"]);
  expect(roles.every((r) => r.school_id !== null)).toBe(true);
  await loginUi(page, wade);
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toBeVisible();
  const choices = page.getByRole("button", { name: /EduLinkage/ });
  await expect(choices).toHaveText(["Collège EduLinkage", "Lycée EduLinkage"].sort());
  await page.getByRole("button", { name: "Lycée EduLinkage" }).click();
  await expect(page.getByRole("heading", { name: "Choisissez une école" })).toHaveCount(0);
  // Jamais d'accès implicite à l'école principale de l'organisation (autre administrateur).
  const complexeId = (await created.json()).school.id as string;
  const forbidden = await request.get(`${API}/api/v1/students?school_id=${complexeId}`, {
    headers: { Authorization: `Bearer ${wadeToken}` },
  });
  expect(forbidden.status()).toBe(403);
});

test("Partenaire : réutilisation scopée et administrateur org-wide déjà couvrant", async ({ page, request }) => {
  const ownerEmail = `${unique("r20ownerp").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const ownerToken = await token(request, ownerEmail);
  const partnerEmail = `${unique("r20partner").toLowerCase()}@platform-e2e.example`;
  const partnerCreated = await request.post(`${API}/api/v1/platform/partners`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: { display_name: "Agence Reuse", full_name: "Contact Reuse", email: partnerEmail },
  });
  expect(partnerCreated.status()).toBe(201);
  const reset = await request.post(`${API}/api/v1/auth/reset-password`, {
    data: { token: (await partnerCreated.json()).dev_reset_token, new_password: PASSWORD },
  });
  expect(reset.status()).toBe(204);
  const partnerToken = await token(request, partnerEmail);
  const orgName = `Groupe Partenaire Reuse ${unique("")}`;
  const firstAdmin = `${unique("orgwide").toLowerCase()}@platform-e2e.example`;
  const enrolled = await request.post(`${API}/api/v1/partner/schools`, {
    headers: { Authorization: `Bearer ${partnerToken}` },
    data: orgPayload(orgName, firstAdmin),
  });
  expect(enrolled.status(), await enrolled.text()).toBe(201);

  await loginUi(page, partnerEmail);
  await expect(page).toHaveURL("/partner");
  await page.goto("/partner/schools");
  await page.getByRole("radio", { name: "Organisation existante" }).check();
  await page.getByRole("combobox").selectOption({ label: orgName });

  // Admin org-wide (premier admin) : il couvre déjà la nouvelle école, aucun rôle ajouté.
  await addSchool(page, "Collège Partenaire", firstAdmin, true);
  await expect(
    page.getByText(`${firstAdmin} administre déjà tous les établissements de cette organisation`, { exact: false }),
  ).toBeVisible();

  // Nouvel admin pour le Lycée, puis réutilisation de ce même compte pour l'Annexe.
  const scoped = `${unique("scopedp").toLowerCase()}@platform-e2e.example`;
  await addSchool(page, "Lycée Partenaire", scoped, false);
  await expect(page.getByText(/Établissement « Lycée Partenaire » inscrit dans/)).toBeVisible();
  await addSchool(page, "Annexe Partenaire", scoped, true);
  await expect(page.getByText(`Compte administrateur existant réutilisé : ${scoped}`, { exact: false })).toBeVisible();

  const scopedToken = await token(request, scoped);
  const me = await request.get(`${API}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${scopedToken}` } });
  expect(((await me.json()).roles as unknown[]).length).toBe(2);
  const schools = await request.get(`${API}/api/v1/partner/schools`, { headers: { Authorization: `Bearer ${partnerToken}` } });
  expect(((await schools.json()) as Array<{ school_name: string }>).map((s) => s.school_name).sort()).toEqual(
    ["Annexe Partenaire", "Collège Partenaire", "Complexe scolaire EDULINKAGE", "Lycée Partenaire"].sort(),
  );
});
