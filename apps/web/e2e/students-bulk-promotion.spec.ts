import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, type TenantAdmin } from "./helpers/tenants";

// Sprint "Réinscription et promotion en masse" : workflow en étapes (années -> mapping -> élèves
// -> aperçu -> confirmation -> résultat) sur /promotions.

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
  request: APIRequestContext, admin: TenantAdmin, yearId: string, levelName: string, className: string, capacity?: number,
) {
  const level = await api(request, admin.orgAdminToken, "POST", "/api/v1/education-levels", {
    school_id: admin.schoolId, name: `${levelName}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  });
  return api(request, admin.orgAdminToken, "POST", "/api/v1/classes", {
    academic_year_id: yearId, education_level_id: level.id, name: className,
    ...(capacity !== undefined ? { capacity } : {}),
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

test("parcours complet : années -> mapping -> élèves -> aperçu -> confirmation -> résultat", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "promoflow");
  const { sourceYear, targetYear } = await setupYears(request, admin);
  const sourceClass = await createClass(request, admin, sourceYear.id, "CM1", "CM1 A");
  const targetClass = await createClass(request, admin, targetYear.id, "CM2", "CM2 A", 30);
  const student = await createStudent(request, admin, "PF-001", "Un");
  await enrollInClass(request, admin, [student.id], sourceYear.id, sourceClass.id);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.getByRole("link", { name: "Réinscriptions" }).click();
  await expect(page).toHaveURL("/promotions");

  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  await page.getByLabel("Classe cible pour CM1 A").selectOption({ label: "CM2 A" });
  await page.getByTestId("promotion-mapping-next").click();

  await expect(page.getByTestId("promotion-selected-count")).toContainText("0 élève");
  await page.locator("tbody tr", { hasText: "PF-001" }).getByRole("checkbox", { name: /Sélectionner/ }).check();
  await expect(page.getByTestId("promotion-selected-count")).toContainText("1 élève");
  await page.getByTestId("promotion-students-next").click();

  await expect(page.getByTestId("promotion-preview-promoted")).toContainText("Promus : 1");
  await expect(page.getByTestId("promotion-preview")).toContainText("CM2 A");
  await page.getByTestId("promotion-confirm").click();

  await expect(page.getByTestId("promotion-result-summary")).toContainText("1 élève traité");

  // Vérification : l'élève apparaît maintenant dans CM2 A pour la liste (via GET /students enrichi).
  const enrollments = await api(request, admin.orgAdminToken, "GET", `/api/v1/students/${student.id}/enrollments`);
  const targetEnrollment = enrollments.find((e: { academic_year_id: string }) => e.academic_year_id === targetYear.id);
  expect(targetEnrollment).toBeTruthy();
  expect(targetEnrollment.class_id).toBe(targetClass.id);
  expect(targetEnrollment.promotion_type).toBe("PROMOTED");

  await page.getByTestId("promotion-done").click();
  await expect(page.getByTestId("promotion-years-next")).toBeVisible();
});

test("classes sans correspondance détectées, capacité insuffisante empêche la confirmation", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "promocapacity");
  const { sourceYear, targetYear } = await setupYears(request, admin);
  const sourceClassA = await createClass(request, admin, sourceYear.id, "CM1", "CM1 A");
  await createClass(request, admin, sourceYear.id, "CM1", "CM1 B");
  await createClass(request, admin, targetYear.id, "CM2", "CM2 A", 1);
  const studentA = await createStudent(request, admin, "PC-001", "Un");
  const studentB = await createStudent(request, admin, "PC-002", "Deux");
  await enrollInClass(request, admin, [studentA.id], sourceYear.id, sourceClassA.id);
  await enrollInClass(request, admin, [studentB.id], sourceYear.id, sourceClassA.id);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");

  await page.getByLabel("Année source").selectOption({ label: "2026-2027" });
  await page.getByLabel("Année cible").selectOption({ label: "2027-2028" });
  await page.getByTestId("promotion-years-next").click();

  await expect(page.getByTestId("promotion-unmapped-notice")).toContainText("CM1 B");
  await page.getByLabel("Classe cible pour CM1 A").selectOption({ label: "CM2 A" });
  await page.getByTestId("promotion-mapping-next").click();

  await page.getByRole("checkbox", { name: "Tout sélectionner" }).check();
  await expect(page.getByTestId("promotion-selected-count")).toContainText("2 élèves");
  await page.getByTestId("promotion-students-next").click();

  await expect(page.getByTestId("promotion-blocking-errors")).toContainText("CM2 A");
  await expect(page.getByTestId("promotion-confirm")).toBeDisabled();
});

test("responsive : assistant de réinscription reste utilisable en mobile/tablette/desktop", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "promoresponsive");
  await setupYears(request, admin);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/promotions");

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 820, height: 1180 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.getByLabel("Année source")).toBeVisible();
    const hasHorizontalScroll = await page.evaluate(() => {
      const main = document.querySelector("main");
      return !!main && main.scrollWidth > main.clientWidth + 1;
    });
    expect(hasHorizontalScroll).toBe(false);
  }
});
