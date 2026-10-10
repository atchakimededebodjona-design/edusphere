import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// suivi plateforme (ajustement produit) — agrégats élèves visibles par PLATFORM_OWNER (/platform/schools :
// colonnes « Élèves » et « Élèves actifs ») et PARTNER_ADMIN (/partner/schools : colonne
// « Élèves »), rendus réellement dans le navigateur, SANS jamais aucune donnée individuelle
// d'élève dans les réponses de ces endpoints, et sans régression sur le blocage de /students.
// Le compte PLATFORM_OWNER n'a aucun flux produit de création : créé directement en base, même
// mécanisme que platform-owner-partner.spec.ts / platform-admin.spec.ts.
const API = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";
const PASSWORD = "SuperSecret123";

test.describe.configure({ mode: "serial" });

let counter = 0;
function unique(prefix: string): string {
  counter += 1;
  return `${prefix}${Date.now()}${counter}${Math.floor(Math.random() * 10000)}`;
}

// Optionnel : nom d'un conteneur API isolé (ex. conteneur éphémère lancé depuis un autre worktree,
// code monté en lecture seule). Si défini, le script de préparation y est exécuté via stdin
// (`docker exec -i -w /app <conteneur> python -`) au lieu du service `api` de la stack compose —
// évite d'écrire dans un conteneur qui n'appartient pas au code testé. Absent : comportement
// historique inchangé (service compose `api`).
const API_CONTAINER = process.env.PLAYWRIGHT_API_CONTAINER;

function runInApiContainer(script: string): void {
  if (API_CONTAINER) {
    execFileSync("docker", ["exec", "-i", "-w", "/app", API_CONTAINER, "python", "-"], { input: script });
    return;
  }
  const tmpFile = path.join(os.tmpdir(), `student_aggregates_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerPath = `/app/student_aggregates_e2e_${unique("")}.py`;
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
      `            full_name="Owner Aggregates E2E", hashed_password=hash_password(${JSON.stringify(PASSWORD)}),`,
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

function enrollmentPayload(prefix: string, schoolName: string, adminEmail: string) {
  return {
    organization: { name: `${schoolName} Groupe`, slug: unique(prefix).toLowerCase(), country_code: "TG" },
    school: { name: schoolName, slug: "principale" },
    admin: { full_name: `Admin ${prefix}`, email: adminEmail, password: PASSWORD },
  };
}

type Student = { id: string; matricule: string; first_name: string; last_name: string; date_of_birth: string };

async function addStudents(request: APIRequestContext, adminToken: string, schoolId: string, n: number): Promise<Student[]> {
  const marker = unique("Ident");
  const students: Student[] = [];
  for (let i = 0; i < n; i += 1) {
    const response = await request.post(`${API}/api/v1/students`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        school_id: schoolId,
        matricule: `${marker}M${i}`,
        first_name: `${marker}Prenom${i}`,
        last_name: `${marker}Nom${i}`,
        date_of_birth: `2014-0${i + 1}-1${i}`,
        sex: i % 2 ? "F" : "M",
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    students.push(await response.json());
  }
  return students;
}

function assertNoIndividualData(body: string, students: Student[]): void {
  for (const s of students) {
    for (const value of [s.id, s.matricule, s.first_name, s.last_name, s.date_of_birth]) {
      expect(body, `valeur individuelle « ${value} » présente dans la réponse`).not.toContain(value);
    }
  }
}

async function loginUi(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

test("PLATFORM_OWNER : colonnes « Élèves » et « Élèves actifs » sur /platform/schools, aucune donnée individuelle, /students toujours bloqué", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("owneragg").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const ownerToken = await token(request, ownerEmail);

  // École inscrite par le propriétaire + 3 élèves, dont 1 retiré (actifs = 2).
  const schoolName = `Ecole Agg ${unique("")}`;
  const adminEmail = `${unique("adminagg").toLowerCase()}@platform-e2e.example`;
  const created = await request.post(`${API}/api/v1/platform/organizations`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: enrollmentPayload("ownagg", schoolName, adminEmail),
  });
  expect(created.status(), await created.text()).toBe(201);
  const schoolId = (await created.json()).school.id as string;
  const adminToken = await token(request, adminEmail);
  const students = await addStudents(request, adminToken, schoolId, 3);
  const withdrawn = await request.patch(`${API}/api/v1/students/${students[0].id}`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { status: "WITHDRAWN", status_change_reason: "E2E agrégats" },
  });
  expect(withdrawn.status(), await withdrawn.text()).toBe(200);

  // Rendu réel dans le navigateur + capture du corps de réponse de l'API d'agrégation.
  await loginUi(page, ownerEmail);
  await expect(page).toHaveURL("/dashboard");
  const schoolsResponse = page.waitForResponse(
    (r) => r.url().includes("/api/v1/platform/schools") && r.request().method() === "GET",
  );
  await page.goto("/platform/schools");
  const body = await (await schoolsResponse).text();
  assertNoIndividualData(body, students);
  const item = (JSON.parse(body).items as Array<Record<string, unknown>>).find((s) => s.id === schoolId);
  expect(item).toBeDefined();
  expect(Object.keys(item!).sort()).toEqual(
    ["acquisition_source", "active_student_count", "created_at", "id", "name", "organization_id", "slug", "student_count"].sort(),
  );

  const headers = page.getByRole("columnheader");
  await expect(headers).toHaveText(["Nom", "Source", "Élèves", "Élèves actifs", "Créée le"]);
  const row = page.getByRole("row").filter({ hasText: schoolName });
  await expect(row).toHaveCount(1);
  const cells = row.getByRole("cell");
  await expect(cells.nth(0)).toHaveText(schoolName);
  await expect(cells.nth(1)).toHaveText("Inscription directe");
  await expect(cells.nth(2)).toHaveText("3");
  await expect(cells.nth(3)).toHaveText("2");
  assertNoIndividualData(await page.content(), students);

  // Tableau de bord : total agrégé « Élèves » toujours présent, jamais de donnée individuelle.
  const dashboardResponse = page.waitForResponse((r) => r.url().includes("/api/v1/platform/dashboard"));
  await page.goto("/dashboard");
  const dashboardBody = await (await dashboardResponse).text();
  assertNoIndividualData(dashboardBody, students);
  expect(typeof JSON.parse(dashboardBody).student_count).toBe("number");
  await expect(page.getByText("Élèves", { exact: true })).toBeVisible();

  // /students : API 403 (RBAC), UI redirigée vers l'espace plateforme.
  for (const url of [
    `${API}/api/v1/students?school_id=${schoolId}`,
    `${API}/api/v1/students/${students[1].id}`,
  ]) {
    const response = await request.get(url, { headers: { Authorization: `Bearer ${ownerToken}` } });
    expect(response.status(), url).toBe(403);
    assertNoIndividualData(await response.text(), students);
  }
  await page.goto("/students");
  await expect(page).toHaveURL("/dashboard");
});

test("PARTNER_ADMIN : colonne « Élèves » sur /partner/schools, aucune donnée individuelle, /students toujours bloqué", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("owneragp").toLowerCase()}@platform-e2e.example`;
  createPlatformOwner(ownerEmail);
  const ownerToken = await token(request, ownerEmail);

  const partnerEmail = `${unique("partneragg").toLowerCase()}@platform-e2e.example`;
  const partnerCreated = await request.post(`${API}/api/v1/platform/partners`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: { display_name: "Agence Agrégats", full_name: "Contact Agrégats", email: partnerEmail },
  });
  expect(partnerCreated.status(), await partnerCreated.text()).toBe(201);
  const reset = await request.post(`${API}/api/v1/auth/reset-password`, {
    data: { token: (await partnerCreated.json()).dev_reset_token, new_password: PASSWORD },
  });
  expect(reset.status()).toBe(204);
  const partnerToken = await token(request, partnerEmail);

  const schoolName = `Ecole Partenaire Agg ${unique("")}`;
  const adminEmail = `${unique("adminagp").toLowerCase()}@platform-e2e.example`;
  const enrolled = await request.post(`${API}/api/v1/partner/schools`, {
    headers: { Authorization: `Bearer ${partnerToken}` },
    data: enrollmentPayload("partagg", schoolName, adminEmail),
  });
  expect(enrolled.status(), await enrolled.text()).toBe(201);
  const schoolId = (await enrolled.json()).school.id as string;
  const students = await addStudents(request, await token(request, adminEmail), schoolId, 2);

  await loginUi(page, partnerEmail);
  await expect(page).toHaveURL("/partner");
  const schoolsResponse = page.waitForResponse(
    (r) => r.url().includes("/api/v1/partner/schools") && r.request().method() === "GET",
  );
  await page.goto("/partner/schools");
  const body = await (await schoolsResponse).text();
  assertNoIndividualData(body, students);
  const items = JSON.parse(body) as Array<Record<string, unknown>>;
  expect(items.map((s) => s.school_id)).toEqual([schoolId]);
  expect(Object.keys(items[0]).sort()).toEqual(
    [
      "active_student_count",
      "enrolled_at",
      "organization_id",
      "organization_name",
      "school_id",
      "school_name",
      "status",
      "student_count",
    ].sort(),
  );

  await expect(page.getByRole("columnheader")).toHaveText(["École", "Organisation", "Élèves", "Inscrite le", "Statut"]);
  const row = page.getByRole("row").filter({ hasText: schoolName });
  await expect(row).toHaveCount(1);
  await expect(row.getByRole("cell").nth(2)).toHaveText("2");
  assertNoIndividualData(await page.content(), students);

  // /students : API 403/404 (RLS masque déjà la ressource au partenaire), UI redirigée vers /partner.
  for (const url of [
    `${API}/api/v1/students?school_id=${schoolId}`,
    `${API}/api/v1/students/${students[0].id}`,
  ]) {
    const response = await request.get(url, { headers: { Authorization: `Bearer ${partnerToken}` } });
    expect([403, 404], url).toContain(response.status());
    assertNoIndividualData(await response.text(), students);
  }
  await page.goto("/students");
  await expect(page).toHaveURL("/partner");
});
