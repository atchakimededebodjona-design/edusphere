import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import {
  API_BASE_URL,
  assignExtraRole,
  clearResetPasswordRateLimit,
  createOrganizationViaPlatform,
  TENANT_PASSWORD,
  unique,
} from "./helpers/tenants";

// Scénario principal du portail enseignant. Toute la mise en place passe par l'API (école, classes,
// matières, élèves, affectation). Le navigateur ne fait que se connecter comme un enseignant réel.

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

async function api(request: APIRequestContext, token: string, method: "GET" | "POST", path: string, data?: unknown) {
  const response = await request.fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.status(), `${method} ${path} → ${await response.text()}`).toBeLessThan(300);
  return response.json();
}

async function setupTeacherScenario(request: APIRequestContext) {
  const admin = await createOrganizationViaPlatform(request, "tpe2e");
  const token = admin.orgAdminToken;
  const schoolId = admin.schoolId;
  const year = await api(request, token, "POST", "/api/v1/academic-years", {
    school_id: schoolId,
    name: unique("AY"),
    start_date: "2026-09-01",
    end_date: "2027-06-30",
    is_current: true,
  });
  const term = await api(request, token, "POST", "/api/v1/academic-terms", {
    academic_year_id: year.id,
    name: "Trimestre 1",
    start_date: "2026-09-01",
    end_date: "2026-12-20",
    order_index: 1,
  });
  const level = await api(request, token, "POST", "/api/v1/education-levels", { school_id: schoolId, name: "CM2" });
  const maths = await api(request, token, "POST", "/api/v1/subjects", { school_id: schoolId, name: "Mathématiques" });
  const histoire = await api(request, token, "POST", "/api/v1/subjects", { school_id: schoolId, name: "Histoire" });
  const classA = await api(request, token, "POST", "/api/v1/classes", {
    academic_year_id: year.id,
    education_level_id: level.id,
    name: "CM2-A",
  });
  const classB = await api(request, token, "POST", "/api/v1/classes", {
    academic_year_id: year.id,
    education_level_id: level.id,
    name: "CM2-B",
  });
  await api(request, token, "POST", `/api/v1/classes/${classA.id}/subjects`, { subject_id: maths.id, coefficient: 2 });
  await api(request, token, "POST", `/api/v1/classes/${classB.id}/subjects`, { subject_id: histoire.id, coefficient: 1 });

  const teacherEmail = `${unique("prof").toLowerCase()}@wizard-e2e.example`;
  const created = await api(request, token, "POST", "/api/v1/users", {
    email: teacherEmail,
    full_name: "Koffi Enseignant",
    school_id: schoolId,
    role_code: "TEACHER",
  });
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: TENANT_PASSWORD },
  });
  await api(request, token, "POST", `/api/v1/classes/${classA.id}/teachers`, { user_id: created.user.id, subject_id: maths.id });

  const studentA = await api(request, token, "POST", "/api/v1/students", {
    school_id: schoolId,
    matricule: unique("MA").toUpperCase(),
    first_name: "Ama",
    last_name: "Alpha",
    date_of_birth: "2014-03-04",
    sex: "F",
  });
  await api(request, token, "POST", `/api/v1/students/${studentA.id}/enrollments`, {
    class_id: classA.id,
    academic_year_id: year.id,
    enrollment_date: "2026-09-01",
  });
  const studentB = await api(request, token, "POST", "/api/v1/students", {
    school_id: schoolId,
    matricule: unique("MB").toUpperCase(),
    first_name: "Binta",
    last_name: "Beta",
    date_of_birth: "2014-05-06",
    sex: "F",
  });
  await api(request, token, "POST", `/api/v1/students/${studentB.id}/enrollments`, {
    class_id: classB.id,
    academic_year_id: year.id,
    enrollment_date: "2026-09-01",
  });

  return { teacherEmail, classA, classB, termName: term.name, studentA, studentB };
}

async function loginTeacher(page: Page, email: string) {
  // Connexion réelle via /login ; un enseignant pur est attendu sur /teacher (pas /dashboard).
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/teacher");
  await expect(page.getByText("Classes affectées")).toBeVisible();
}

test("portail enseignant : connexion, classes, élèves, présences, notes, bulletins et périmètre", async ({ page, request }) => {
  const scenario = await setupTeacherScenario(request);

  // Connexion d'un compte TEACHER pur : arrivée directe sur /teacher.
  await loginTeacher(page, scenario.teacherEmail);

  // Mes classes : uniquement la classe affectée.
  await page.getByRole("navigation", { name: "Navigation enseignant" }).getByRole("link", { name: "Mes classes" }).click();
  await expect(page).toHaveURL("/teacher/classes");
  await expect(page.getByRole("heading", { name: "CM2-A" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "CM2-B" })).toHaveCount(0);

  // Détail de la classe : matières de l'enseignant seulement.
  await page.goto(`/teacher/classes/${scenario.classA.id}`);
  await expect(page.getByText("Mathématiques")).toBeVisible();
  await expect(page.getByText("Histoire")).toHaveCount(0);

  // Mes élèves : l'élève de CM2-A est visible, celui de CM2-B ne l'est jamais.
  await page.goto("/teacher/students");
  await expect(page.getByText("Alpha Ama").or(page.getByText("Ama Alpha"))).toBeVisible();
  await expect(page.getByText("Beta", { exact: false })).toHaveCount(0);

  // Présences : la classe est proposée et une session peut être créée.
  await page.goto(`/teacher/attendance?class_id=${scenario.classA.id}`);
  await expect(page.getByRole("heading", { name: "Présences" })).toBeVisible();
  await expect(page.getByRole("combobox").first()).toHaveValue(scenario.classA.id);
  await page.getByRole("button", { name: "Créer la session" }).click();
  await expect(page.getByRole("heading", { name: /Appel du/ })).toBeVisible();

  // Notes : seules les matières affectées sont proposées.
  await page.goto(`/teacher/grades?class_id=${scenario.classA.id}`);
  const subjectSelect = page.getByRole("combobox", { name: "Matière" });
  await expect(subjectSelect.locator("option", { hasText: "Mathématiques" })).toHaveCount(1);
  await expect(subjectSelect.locator("option", { hasText: "Histoire" })).toHaveCount(0);

  // Bulletins : périmètre de la classe (aucun bulletin publié dans ce scénario).
  await page.goto(`/teacher/report-cards?class_id=${scenario.classA.id}`);
  await expect(page.getByText("Aucun bulletin publié pour cette classe.")).toBeVisible();

  // Accès direct à une classe non affectée : refusé avec un message clair (404 côté backend).
  await page.goto(`/teacher/classes/${scenario.classB.id}`);
  await expect(page.getByText("Cette ressource n'est pas accessible avec votre affectation.")).toBeVisible();

  // Le compte enseignant ne voit pas l'espace administratif : /dashboard le renvoie vers /teacher.
  await page.goto("/dashboard");
  await expect(page).toHaveURL("/teacher");
});

test("portail enseignant : accès direct à une élève hors périmètre refusé", async ({ page, request }) => {
  const scenario = await setupTeacherScenario(request);
  await loginTeacher(page, scenario.teacherEmail);

  await page.goto(`/teacher/students/${scenario.studentB.id}`);
  await expect(page.getByText("Cette ressource n'est pas accessible avec votre affectation.")).toBeVisible();
});

test("portail enseignant : régression — justification et motif d'une absence sont enregistrés et relus", async ({
  page,
  request,
}) => {
  const scenario = await setupTeacherScenario(request);
  await loginTeacher(page, scenario.teacherEmail);

  await page.goto(`/teacher/attendance?class_id=${scenario.classA.id}`);
  await page.getByRole("button", { name: "Créer la session" }).click();
  await expect(page.getByRole("heading", { name: /Appel du/ })).toBeVisible();

  await page.getByLabel("Statut de Alpha").selectOption("ABSENT");
  await page.getByLabel("Justifiée").check();
  await page.getByLabel("Motif de Alpha").fill("Certificat médical");
  await page.getByRole("button", { name: "Enregistrer l'appel" }).click();
  await expect(page.getByText("Appel enregistré.")).toBeVisible();

  // Rechargement complet : la session doit être relue avec justified/reason réellement persistés
  // (pas seulement l'état React local).
  await page.reload();
  await page.getByRole("button", { name: new Date().toISOString().slice(0, 10) }).click();
  await expect(page.getByLabel("Statut de Alpha")).toHaveValue("ABSENT");
  await expect(page.getByLabel("Justifiée")).toBeChecked();
  await expect(page.getByLabel("Motif de Alpha")).toHaveValue("Certificat médical");
});

test("compte mixte (SCHOOL_ADMIN + TEACHER) : reste sur /dashboard, avec un accès explicite vers /teacher", async ({
  page,
  request,
}) => {
  const admin = await createOrganizationViaPlatform(request, "tpmixed");
  const me = await api(request, admin.orgAdminToken, "GET", "/api/v1/auth/me");
  assignExtraRole(me.user.id, "TEACHER", admin.orgId, admin.schoolId);

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(admin.orgAdminEmail);
  await page.getByPlaceholder("Mot de passe").fill(admin.password);
  await page.getByRole("button", { name: "Se connecter" }).click();

  // Compte mixte : jamais redirigé automatiquement vers /teacher, il reste sur son espace admin.
  await expect(page).toHaveURL("/dashboard");

  const teacherLink = page.getByRole("link", { name: "Espace enseignant" });
  await expect(teacherLink).toBeVisible();
  await teacherLink.click();
  await expect(page).toHaveURL("/teacher");
});
