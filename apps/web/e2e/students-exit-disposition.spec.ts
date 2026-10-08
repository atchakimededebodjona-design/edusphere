import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, type TenantAdmin } from "./helpers/tenants";

// Sprint "Sortie de l'établissement" : une classe source sans correspondance peut être déclarée
// explicitement en sortie (fin de cycle / transfert / retrait / autre) plutôt que d'être comptée
// silencieusement comme un élève oublié. Jamais de classe fictive créée.

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

async function api(request: APIRequestContext, token: string, method: "GET" | "POST", path: string, data?: unknown) {
  const response = await request.fetch(`${API_BASE_URL}${path}`, { method, headers: { Authorization: `Bearer ${token}` }, data });
  expect(response.status(), `${method} ${path} → ${await response.text()}`).toBeLessThan(300);
  return response.json();
}

async function loginAdmin(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill("SuperSecret123");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");
}

async function setupYears(request: APIRequestContext, admin: TenantAdmin) {
  const sourceYear = await api(request, admin.orgAdminToken, "POST", "/api/v1/academic-years", {
    school_id: admin.schoolId, name: "2026-2027", start_date: "2026-09-01", end_date: "2027-06-30", is_current: true,
  });
  const targetYear = await api(request, admin.orgAdminToken, "POST", "/api/v1/academic-years", {
    school_id: admin.schoolId, name: "2027-2028", start_date: "2027-09-01", end_date: "2028-06-30",
  });
  return { sourceYear, targetYear };
}

async function createClass(
  request: APIRequestContext, admin: TenantAdmin, yearId: string, levelName: string, className: string,
) {
  const level = await api(request, admin.orgAdminToken, "POST", "/api/v1/education-levels", {
    school_id: admin.schoolId, name: `${levelName}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  });
  return api(request, admin.orgAdminToken, "POST", "/api/v1/classes", {
    academic_year_id: yearId, education_level_id: level.id, name: className,
  });
}

async function createStudent(request: APIRequestContext, admin: TenantAdmin, matricule: string, lastName: string) {
  return api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId, matricule, first_name: "Eleve", last_name: lastName,
    date_of_birth: "2015-01-01", sex: "F",
  });
}

async function enrollInClass(request: APIRequestContext, admin: TenantAdmin, studentIds: string[], yearId: string, classId: string) {
  await api(request, admin.orgAdminToken, "POST", "/api/v1/students/bulk-enrollment", {
    student_ids: studentIds, academic_year_id: yearId, class_id: classId, enrollment_date: "2026-09-01",
  });
}

// --- Scénario A : promotion normale (non-régression) --------------------------------------------------
test("CM1 → CM2 : un élève est promu avec succès", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "exitscenarioa");
  const { sourceYear, targetYear } = await setupYears(request, admin);
  const cm1 = await createClass(request, admin, sourceYear.id, "CM1", "CM1");
  const cm2 = await createClass(request, admin, targetYear.id, "CM2", "CM2");
  const student = await createStudent(request, admin, "SCENA-001", "Un");
  await enrollInClass(request, admin, [student.id], sourceYear.id, cm1.id);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");
  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  await page.getByLabel(`Classe cible pour ${cm1.name}`).selectOption({ label: "CM2" });
  await page.getByTestId("promotion-mapping-next").click();
  await page.getByRole("checkbox", { name: "Tout sélectionner" }).check();
  await page.getByTestId("promotion-students-next").click();

  await expect(page.getByTestId("promotion-preview-promoted")).toContainText("Promus : 1");
  await page.getByTestId("promotion-confirm").click();
  await expect(page.getByTestId("promotion-result-summary")).toContainText("1 élève traité");
});

// --- Scénario B : classe terminale déclarée en sortie --------------------------------------------------
test("CM2 sans classe cible : disposition Sortie — Fin de cycle, aperçu, confirmation, résultat", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "exitscenariob");
  const { sourceYear, targetYear } = await setupYears(request, admin);
  const cm2 = await createClass(request, admin, sourceYear.id, "CM2", "CM2");
  void targetYear; // aucune classe cible créée dans l'année cible : exactement le cas CM2 sans correspondance
  const student = await createStudent(request, admin, "SCENB-001", "Un");
  await enrollInClass(request, admin, [student.id], sourceYear.id, cm2.id);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");
  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  await expect(page.getByTestId("promotion-unmapped-notice")).toContainText("CM2");
  await page.getByLabel(`Disposition pour ${cm2.name}`).selectOption({ label: "Sortie — Fin de cycle" });
  await page.getByTestId("promotion-mapping-next").click();

  await page.getByRole("checkbox", { name: "Tout sélectionner" }).check();
  await expect(page.locator("tbody tr", { hasText: "SCENB-001" })).toContainText("Sortie — Fin de cycle");
  await page.getByTestId("promotion-students-next").click();

  await expect(page.getByTestId("promotion-preview-exit")).toContainText("Sortants : 1");
  await expect(page.getByTestId("promotion-exit-breakdown")).toContainText("Fin de cycle : 1");
  await expect(page.getByTestId("promotion-unprocessed-alert")).toHaveCount(0);
  await expect(page.getByTestId("promotion-confirm")).toBeEnabled();

  await page.getByTestId("promotion-confirm").click();
  await expect(page.getByTestId("promotion-result-summary")).toContainText("1 élève traité");
  await expect(page.getByTestId("promotion-result-exit")).toContainText("1 sortant");
  await expect(page.getByTestId("promotion-result-exit-breakdown")).toContainText("fin de cycle");

  // L'inscription historique SOURCE reste intacte, aucune inscription créée pour l'année cible.
  const enrollments = await api(request, admin.orgAdminToken, "GET", `/api/v1/students/${student.id}/enrollments`);
  expect(enrollments).toHaveLength(1);
  expect(enrollments[0].academic_year_id).toBe(sourceYear.id);
  expect(enrollments[0].status).toBe("ACTIVE");

  const exits = await api(request, admin.orgAdminToken, "GET", `/api/v1/students/${student.id}/exits`);
  expect(exits).toHaveLength(1);
  expect(exits[0].exit_type).toBe("GRADUATED");
});

// --- Scénario C : ni mapping ni disposition -> non traité, confirmation bloquée ------------------------
test("CM2 sans mapping ni disposition : avertissement, confirmation désactivée", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "exitscenarioc");
  const { sourceYear, targetYear } = await setupYears(request, admin);
  const cm1 = await createClass(request, admin, sourceYear.id, "CM1", "CM1");
  const cm2 = await createClass(request, admin, targetYear.id, "CM2", "CM2");
  // CM2 (source) n'a ni classe cible ni disposition déclarée — "non traité" explicite.
  const cm2Source = await createClass(request, admin, sourceYear.id, "CM2", "CM2-source");
  const promotedStudent = await createStudent(request, admin, "SCENC-001", "Un");
  const unprocessedStudent = await createStudent(request, admin, "SCENC-002", "Deux");
  await enrollInClass(request, admin, [promotedStudent.id], sourceYear.id, cm1.id);
  await enrollInClass(request, admin, [unprocessedStudent.id], sourceYear.id, cm2Source.id);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");
  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  // Seul CM1 est mappé ; CM2-source reste volontairement "Non traité".
  await page.getByLabel(`Classe cible pour ${cm1.name}`).selectOption({ label: "CM2" });
  void cm2;
  await expect(page.getByTestId("promotion-unmapped-notice")).toContainText("CM2-source");
  await page.getByTestId("promotion-mapping-next").click();

  await page.getByRole("checkbox", { name: "Tout sélectionner" }).check();
  await expect(page.locator("tbody tr", { hasText: "SCENC-002" })).toContainText("Non traité");
  await page.getByTestId("promotion-students-next").click();

  await expect(page.getByTestId("promotion-preview-unprocessed")).toContainText("Sans classe cible et non traités : 1");
  await expect(page.getByTestId("promotion-unprocessed-alert")).toContainText(
    "1 élève(s) n'ont ni classe cible ni disposition de sortie.",
  );
  await expect(page.getByTestId("promotion-confirm")).toBeDisabled();
});

// --- Scénario D : responsive ---------------------------------------------------------------------------
test("responsive : étape mapping avec disposition de sortie reste utilisable en mobile/tablette/desktop", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "exitscenariod");
  const { sourceYear } = await setupYears(request, admin);
  await createClass(request, admin, sourceYear.id, "CM2", "CM2");

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");
  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 820, height: 1180 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.getByText("2. Correspondance des classes")).toBeVisible();
    const hasHorizontalScroll = await page.evaluate(() => {
      const main = document.querySelector("main");
      return !!main && main.scrollWidth > main.clientWidth + 1;
    });
    expect(hasHorizontalScroll).toBe(false);
  }
});
