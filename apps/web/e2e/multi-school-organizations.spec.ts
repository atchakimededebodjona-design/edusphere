import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// PR #19 — plusieurs établissements par organisation, parcours réels dans le navigateur :
// - PLATFORM_OWNER : organisation + Primaire (formulaire historique), puis « Organisation
//   existante » → sélection → ajout du Collège ; une seule organisation, deux établissements ;
// - PARTNER_ADMIN : même chose dans son périmètre, compteurs élèves (agrégats), refus backend d'une
//   organisation étrangère.
// Toujours vérifié : aucune donnée individuelle d'élève dans les réponses, /students bloqué.
const API = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";
// Conteneur API isolé optionnel (voir platform-student-aggregates.spec.ts) : le script de
// préparation y est exécuté via stdin plutôt que dans le service `api` de la stack compose.
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
  const tmpFile = path.join(os.tmpdir(), `multi_school_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerPath = `/app/multi_school_e2e_${unique("")}.py`;
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
      `            full_name="Owner Multi-School E2E", hashed_password=hash_password(${JSON.stringify(PASSWORD)}),`,
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

async function token(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/api/v1/auth/login`, { data: { email, password: PASSWORD } });
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

async function fillNewSchoolForm(page: Page, schoolName: string, adminEmail: string): Promise<void> {
  await page.getByLabel("Nom du nouvel établissement").fill(schoolName);
  await page.getByLabel("Nom de l'administrateur").fill(`Admin ${schoolName}`);
  await page.getByLabel("Email de l'administrateur").fill(adminEmail);
  await page.getByLabel("Mot de passe initial de l'administrateur").fill(PASSWORD);
  await page.getByLabel("Confirmation du mot de passe de l'administrateur").fill(PASSWORD);
  await page.getByRole("button", { name: "Ajouter l'établissement" }).click();
}

async function addStudent(request: APIRequestContext, adminToken: string, schoolId: string, marker: string, i: number) {
  const response = await request.post(`${API}/api/v1/students`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: {
      school_id: schoolId,
      matricule: `${marker}M${i}`,
      first_name: `${marker}Prenom${i}`,
      last_name: `${marker}Nom${i}`,
      date_of_birth: "2014-02-03",
      sex: "F",
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as { id: string };
}

test("PLATFORM_OWNER : organisation + Primaire, puis ajout du Collège à l'organisation existante", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("msowner").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const orgName = `Groupe Scolaire La Reference ${unique("")}`;
  const orgSlug = unique("gs-ref").toLowerCase();

  // 1. Organisation + Primaire via le formulaire historique (« Nouvelle organisation »).
  await loginUi(page, ownerEmail);
  await expect(page).toHaveURL("/dashboard");
  await page.getByRole("link", { name: "+ Inscrire une organisation" }).click();
  await expect(page.getByRole("radio", { name: "Nouvelle organisation" })).toBeChecked();
  await page.getByLabel("Nom de l'organisation").fill(orgName);
  await page.getByLabel("Slug").first().fill(orgSlug);
  await page.getByLabel("Nom de l'école").fill("Primaire La Reference");
  await page.getByLabel("Slug").nth(1).fill("primaire");
  await page.getByLabel("Nom complet").fill("Admin Primaire");
  await page.getByLabel("Email").last().fill(`${unique("adminprim").toLowerCase()}@platform-e2e.example`);
  await page.getByLabel("Mot de passe initial").fill(PASSWORD);
  await page.getByLabel("Confirmation du mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Créer l'organisation" }).click();
  await expect(page.getByRole("heading", { name: "Organisation créée avec succès" })).toBeVisible();

  // 2-4. Parcours « Organisation existante » depuis le tableau de bord → sélection → Collège.
  await page.goto("/dashboard");
  await page.getByRole("link", { name: "+ Ajouter un établissement" }).click();
  await expect(page.getByRole("radio", { name: "Organisation existante" })).toBeChecked();
  await expect(page.getByRole("heading", { name: "Ajouter un établissement à une organisation existante" })).toBeVisible();
  await page.getByLabel("Rechercher une organisation existante").fill(orgName);
  await page.getByRole("button", { name: "Rechercher" }).click();
  const results = page.getByRole("list", { name: "Organisations trouvées" }).getByRole("button");
  await expect(results).toHaveCount(1);
  await results.first().click();
  const selected = page.getByRole("region", { name: "Organisation sélectionnée" });
  await expect(selected.getByText(orgName, { exact: true })).toBeVisible();
  const existing = selected.getByRole("list", { name: "Établissements existants" });
  await expect(existing.getByRole("listitem")).toHaveText(["✓ Primaire La Reference"]);
  // Aucun champ d'organisation dans ce parcours : impossible de « recréer » l'organisation.
  await expect(page.getByLabel("Nom de l'organisation")).toHaveCount(0);
  await fillNewSchoolForm(page, "College La Reference", `${unique("admincol").toLowerCase()}@platform-e2e.example`);
  await expect(page.getByText(/Établissement « College La Reference » ajouté à/)).toBeVisible();

  // 5. À l'écran : organisation unique, Primaire + Collège.
  await expect(existing.getByRole("listitem")).toHaveText(["✓ Primaire La Reference", "✓ College La Reference"]);
  const ownerToken = await token(request, ownerEmail);
  const search = await request.get(`${API}/api/v1/platform/organizations?q=${encodeURIComponent(orgName)}`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  const found = await search.json();
  expect(found.total).toBe(1);
  const orgSchools = await request.get(`${API}/api/v1/platform/organizations/${found.items[0].id}/schools`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  const body = await orgSchools.json();
  expect(body.schools.map((s: { name: string }) => s.name)).toEqual(["Primaire La Reference", "College La Reference"]);
  expect(body.schools.map((s: { acquisition_source: string }) => s.acquisition_source)).toEqual([
    "PLATFORM_OWNER",
    "PLATFORM_OWNER",
  ]);

  // /students reste bloqué pour le propriétaire (API 403, UI redirigée).
  const studentsResponse = await request.get(`${API}/api/v1/students?school_id=${body.schools[1].id}`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  expect(studentsResponse.status()).toBe(403);
  await page.goto("/students");
  await expect(page).toHaveURL("/dashboard");
});

test("PARTNER_ADMIN : organisation + Primaire, ajout du Collège, compteurs élèves, organisation étrangère refusée", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("msownerp").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const ownerToken = await token(request, ownerEmail);

  async function newPartner(prefix: string): Promise<{ email: string; token: string }> {
    const email = `${unique(prefix).toLowerCase()}@platform-e2e.example`;
    const created = await request.post(`${API}/api/v1/platform/partners`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: { display_name: `Agence ${prefix}`, full_name: `Contact ${prefix}`, email },
    });
    expect(created.status(), await created.text()).toBe(201);
    const reset = await request.post(`${API}/api/v1/auth/reset-password`, {
      data: { token: (await created.json()).dev_reset_token, new_password: PASSWORD },
    });
    expect(reset.status()).toBe(204);
    return { email, token: await token(request, email) };
  }

  const partnerA = await newPartner("mspa");
  const partnerB = await newPartner("mspb");
  // Organisation étrangère : inscrite par le partenaire B (via l'API).
  const foreign = await request.post(`${API}/api/v1/partner/schools`, {
    headers: { Authorization: `Bearer ${partnerB.token}` },
    data: {
      organization: { name: `Organisation Y ${unique("")}`, slug: unique("org-y").toLowerCase(), country_code: "TG" },
      school: { name: "Lycee Y", slug: "principale" },
      admin: { full_name: "Admin Y", email: `${unique("admy").toLowerCase()}@platform-e2e.example`, password: PASSWORD },
    },
  });
  expect(foreign.status(), await foreign.text()).toBe(201);
  const foreignOrgId = (await foreign.json()).organization.id as string;

  // 1. Partenaire A : organisation + Primaire via le formulaire « Nouvelle organisation ».
  const orgName = `Groupe Partenaire ${unique("")}`;
  const primaryAdminEmail = `${unique("pprim").toLowerCase()}@platform-e2e.example`;
  await loginUi(page, partnerA.email);
  await expect(page).toHaveURL("/partner");
  await page.goto("/partner/schools");
  await expect(page.getByRole("radio", { name: "Nouvelle organisation" })).toBeChecked();
  await page.getByPlaceholder("Nom de l'organisation").fill(orgName);
  await page.getByPlaceholder("Identifiant (ex. groupe-scolaire-x)").fill(unique("gp").toLowerCase());
  await page.getByPlaceholder("Nom de l'école").fill("Primaire Partenaire");
  await page.getByPlaceholder("Nom de l'administrateur").fill("Admin Primaire Partenaire");
  await page.getByPlaceholder("Email de l'administrateur").fill(primaryAdminEmail);
  await page.getByPlaceholder("Mot de passe initial (8 caractères min.)").fill(PASSWORD);
  await page.getByRole("button", { name: "Inscrire l'école" }).click();
  await expect(page.getByText("École « Primaire Partenaire » inscrite.", { exact: false })).toBeVisible();

  // 2. « Organisation existante » : seules SES organisations sont proposées.
  const orgsResponse = page.waitForResponse((r) => r.url().includes("/api/v1/partner/organizations"));
  await page.getByRole("radio", { name: "Organisation existante" }).check();
  const select = page.getByRole("combobox");
  await expect(select).toBeVisible();
  const orgsBody = await (await orgsResponse).text();
  expect(orgsBody).not.toContain(foreignOrgId);
  const optionTexts = await select.locator("option").allTextContents();
  expect(optionTexts.filter((t) => !t.startsWith("—"))).toEqual([orgName]);
  await select.selectOption({ label: orgName });
  const selected = page.getByRole("region", { name: "Organisation sélectionnée" });
  await expect(selected.getByRole("list", { name: "Établissements existants" }).getByRole("listitem")).toHaveText([
    "✓ Primaire Partenaire",
  ]);
  const collegeAdminEmail = `${unique("pcol").toLowerCase()}@platform-e2e.example`;
  await fillNewSchoolForm(page, "College Partenaire", collegeAdminEmail);
  await expect(page.getByText(/Établissement « College Partenaire » inscrit dans/)).toBeVisible();

  // 3-4. Les deux écoles apparaissent, avec les compteurs élèves (agrégats uniquement).
  const schools = await request.get(`${API}/api/v1/partner/schools`, {
    headers: { Authorization: `Bearer ${partnerA.token}` },
  });
  const schoolList = (await schools.json()) as Array<{ school_id: string; school_name: string; organization_id: string }>;
  expect(schoolList.map((s) => s.school_name).sort()).toEqual(["College Partenaire", "Primaire Partenaire"]);
  expect(new Set(schoolList.map((s) => s.organization_id)).size).toBe(1);
  const byName = Object.fromEntries(schoolList.map((s) => [s.school_name, s.school_id]));
  const marker = unique("Ident");
  const primaryToken = await token(request, primaryAdminEmail);
  const collegeToken = await token(request, collegeAdminEmail);
  const students = [
    await addStudent(request, primaryToken, byName["Primaire Partenaire"], marker, 0),
    await addStudent(request, primaryToken, byName["Primaire Partenaire"], marker, 1),
    await addStudent(request, collegeToken, byName["College Partenaire"], marker, 2),
  ];
  const listResponse = page.waitForResponse(
    (r) => r.url().includes("/api/v1/partner/schools") && r.request().method() === "GET",
  );
  await page.reload();
  const listBody = await (await listResponse).text();
  expect(listBody).not.toContain(marker);
  for (const s of students) expect(listBody).not.toContain(s.id);
  for (const [name, count] of [
    ["Primaire Partenaire", "2"],
    ["College Partenaire", "1"],
  ]) {
    const row = page.getByRole("row").filter({ hasText: name });
    await expect(row).toHaveCount(1);
    await expect(row.getByRole("cell").nth(2)).toHaveText(count);
  }
  assertNoMarker(await page.content(), marker);

  // 5-6. Organisation étrangère : refus backend (404, aucune école créée), même via l'API directe.
  const attempt = await request.post(`${API}/api/v1/partner/organizations/${foreignOrgId}/schools`, {
    headers: { Authorization: `Bearer ${partnerA.token}` },
    data: {
      school: { name: "Intrus", slug: "intrus" },
      admin: { full_name: "Intrus", email: `${unique("intrus").toLowerCase()}@platform-e2e.example`, password: PASSWORD },
    },
  });
  expect(attempt.status()).toBe(404);
  const foreignView = await request.get(`${API}/api/v1/platform/organizations/${foreignOrgId}/schools`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
  });
  expect(((await foreignView.json()).schools as unknown[]).length).toBe(1);

  // /students reste bloqué pour le partenaire (API 403/404, UI redirigée vers /partner).
  for (const url of [`${API}/api/v1/students?school_id=${byName["College Partenaire"]}`, `${API}/api/v1/students/${students[2].id}`]) {
    const response = await request.get(url, { headers: { Authorization: `Bearer ${partnerA.token}` } });
    expect([403, 404]).toContain(response.status());
    assertNoMarker(await response.text(), marker);
  }
  await page.goto("/students");
  await expect(page).toHaveURL("/partner");
});

function assertNoMarker(body: string, marker: string): void {
  expect(body, "donnée individuelle d'élève présente").not.toContain(marker);
}
