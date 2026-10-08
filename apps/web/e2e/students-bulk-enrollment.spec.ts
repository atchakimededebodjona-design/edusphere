import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, type TenantAdmin } from "./helpers/tenants";

// Sprint "Affectation en masse des élèves aux classes" : colonne Classe, filtre "Non affectés",
// panneau d'affectation en masse (nouveaux/réaffectés/inchangés, capacité).

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

async function setupYearAndClass(
  request: APIRequestContext,
  admin: TenantAdmin,
  className: string,
  capacity?: number,
) {
  const year = await api(request, admin.orgAdminToken, "POST", "/api/v1/academic-years", {
    school_id: admin.schoolId, name: "2026-2027", start_date: "2026-09-01", end_date: "2027-06-30", is_current: true,
  });
  const level = await api(request, admin.orgAdminToken, "POST", "/api/v1/education-levels", {
    school_id: admin.schoolId, name: "CM1",
  });
  const schoolClass = await api(request, admin.orgAdminToken, "POST", "/api/v1/classes", {
    academic_year_id: year.id, education_level_id: level.id, name: className,
    ...(capacity !== undefined ? { capacity } : {}),
  });
  return { year, level, schoolClass };
}

async function createStudent(request: APIRequestContext, admin: TenantAdmin, matricule: string, lastName: string) {
  return api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId, matricule, first_name: "Eleve", last_name: lastName,
    date_of_birth: "2015-01-01", sex: "F",
  });
}

test("colonne Classe, filtre Non affectés, et affectation en masse de nouveaux élèves", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "bulkenroll");
  const { year, schoolClass } = await setupYearAndClass(request, admin, "CM1 A", 30);
  const assigned = await createStudent(request, admin, "BE-001", "Assigne");
  const unassigned = await createStudent(request, admin, "BE-002", "NonAssigne");
  await api(request, admin.orgAdminToken, "POST", `/api/v1/students/${assigned.id}/enrollments`, {
    class_id: schoolClass.id, enrollment_date: "2026-09-01",
  });

  await loginAdmin(page, admin.orgAdminEmail);
  await page.getByRole("link", { name: "Élèves" }).click();
  await expect(page).toHaveURL("/students");

  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Classe", exact: true })).toBeVisible();

  const rowAssigned = page.locator("tbody tr", { hasText: "BE-001" });
  await expect(rowAssigned.getByText("CM1 A", { exact: true })).toBeVisible();
  const rowUnassigned = page.locator("tbody tr", { hasText: "BE-002" });
  await expect(rowUnassigned.getByText("Non affecté", { exact: true })).toBeVisible();

  // Filtre "Non affectés" : seul l'élève sans inscription active apparaît.
  const classFilterSelect = page.getByRole("combobox", { name: "Filtrer par classe" });
  await classFilterSelect.selectOption({ label: "Non affectés" });
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr", { hasText: "BE-002" })).toBeVisible();
  await classFilterSelect.selectOption({ label: "Toutes les classes" });

  // Sélection + affectation en masse du nouvel élève.
  await rowUnassigned.getByRole("checkbox", { name: /Sélectionner/ }).check();
  await expect(page.getByText("1 élève sélectionné")).toBeVisible();
  await page.getByRole("button", { name: "Affecter à une classe" }).click();

  const dialog = page.getByRole("dialog", { name: "Affecter des élèves à une classe" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });
  await dialog.getByLabel("Classe").selectOption({ label: "CM1 A" });

  await expect(dialog.getByTestId("bulk-enrollment-preview")).toContainText("Capacité : 30");
  await expect(dialog.getByTestId("bulk-enrollment-preview")).toContainText("Effectif actuel : 1");
  await expect(dialog.getByTestId("bulk-enrollment-situation")).toContainText("1 nouveau");

  await dialog.getByTestId("bulk-enrollment-confirm").click();
  await expect(dialog.getByTestId("bulk-enrollment-result-summary")).toContainText("1 élève traité");
  await dialog.getByTestId("bulk-enrollment-done").click();

  // Rafraîchissement : la liste et le filtre reflètent immédiatement la nouvelle affectation.
  await expect(page.locator("tbody tr", { hasText: "BE-002" }).getByText("CM1 A", { exact: true })).toBeVisible();
  await expect(page.getByText(/sélectionnés?/)).toHaveCount(0);
});

test("réaffectation : élève déjà dans une classe est reconnu comme inchangé ou réaffecté selon la cible", async ({
  page,
  request,
}) => {
  const admin = await createOrganizationViaPlatform(request, "bulkreassign");
  const { year } = await setupYearAndClass(request, admin, "CM1 A");
  const classB = await api(request, admin.orgAdminToken, "POST", "/api/v1/classes", {
    academic_year_id: year.id,
    education_level_id: (await api(request, admin.orgAdminToken, "GET", `/api/v1/education-levels?school_id=${admin.schoolId}`))[0].id,
    name: "CM1 B",
  });
  const student = await createStudent(request, admin, "BE-010", "Mobile");
  await api(request, admin.orgAdminToken, "POST", `/api/v1/students/${student.id}/enrollments`, {
    class_id: classB.id, enrollment_date: "2026-09-01",
  });

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");

  const row = page.locator("tbody tr", { hasText: "BE-010" });
  await row.getByRole("checkbox", { name: /Sélectionner/ }).check();
  await page.getByRole("button", { name: "Affecter à une classe" }).click();

  const dialog = page.getByRole("dialog", { name: "Affecter des élèves à une classe" });
  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });

  // Même classe (B) : déjà dedans, donc inchangé.
  await dialog.getByLabel("Classe").selectOption({ label: "CM1 B" });
  await expect(dialog.getByTestId("bulk-enrollment-situation")).toContainText("1 déjà dans cette classe");

  // Classe A : réaffectation.
  await dialog.getByLabel("Classe").selectOption({ label: "CM1 A" });
  await expect(dialog.getByTestId("bulk-enrollment-situation")).toContainText("1 réaffectation");
  await dialog.getByTestId("bulk-enrollment-confirm").click();
  await expect(dialog.getByTestId("bulk-enrollment-result-summary")).toBeVisible();
  await dialog.getByTestId("bulk-enrollment-done").click();

  await expect(row.getByText("CM1 A", { exact: true })).toBeVisible();
});

test("capacité insuffisante empêche la confirmation", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "bulkcapacity");
  const { year } = await setupYearAndClass(request, admin, "CM1 A", 1);
  const students = await Promise.all([
    createStudent(request, admin, "BE-020", "Un"),
    createStudent(request, admin, "BE-021", "Deux"),
  ]);

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");

  for (const s of students) {
    await page.locator("tbody tr", { hasText: s.matricule }).getByRole("checkbox", { name: /Sélectionner/ }).check();
  }
  await page.getByRole("button", { name: "Affecter à une classe" }).click();

  const dialog = page.getByRole("dialog", { name: "Affecter des élèves à une classe" });
  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });
  await dialog.getByLabel("Classe").selectOption({ label: "CM1 A" });

  await expect(dialog.getByTestId("bulk-enrollment-capacity-error")).toContainText("Capacité insuffisante");
  await expect(dialog.getByTestId("bulk-enrollment-confirm")).toBeDisabled();
});

// Correction post-audit 3 : l'aperçu (dry-run) ne doit jamais relabelliser une erreur 403/404/
// réseau/500 comme "Capacité insuffisante" — seul un 409 l'est. Le vrai backend ne renvoie pas
// facilement ces statuts via une interaction UI normale (le bouton est déjà masqué sans
// students.manage, etc.) : on intercepte précisément l'appel d'aperçu (dry_run=true) pour simuler
// chaque cas, sans toucher à l'appel de confirmation réel.
async function openPanelWithOneStudent(page: Page, request: APIRequestContext, prefix: string) {
  const admin = await createOrganizationViaPlatform(request, prefix);
  const { year, schoolClass } = await setupYearAndClass(request, admin, "CM1 A", 30);
  const student = await createStudent(request, admin, `${prefix.toUpperCase()}-01`, "Preview");

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");
  await page.locator("tbody tr", { hasText: student.matricule }).getByRole("checkbox", { name: /Sélectionner/ }).check();
  await page.getByRole("button", { name: "Affecter à une classe" }).click();

  const dialog = page.getByRole("dialog", { name: "Affecter des élèves à une classe" });
  return { dialog, year, schoolClass };
}

test("aperçu : une erreur 403 affiche un message de droits, pas 'Capacité insuffisante'", async ({ page, request }) => {
  await page.route("**/api/v1/students/bulk-enrollment*", async (route) => {
    if (route.request().url().includes("dry_run=true")) {
      await route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Not enough permissions" }) });
    } else {
      await route.continue();
    }
  });
  const { dialog, year, schoolClass } = await openPanelWithOneStudent(page, request, "previewforbidden");

  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });
  await dialog.getByLabel("Classe").selectOption({ label: schoolClass.name });

  const errorBlock = dialog.getByTestId("bulk-enrollment-preview-error");
  await expect(errorBlock).toContainText("Vous n'avez pas les droits nécessaires.");
  await expect(dialog.getByTestId("bulk-enrollment-capacity-error")).toHaveCount(0);
  await expect(dialog.getByTestId("bulk-enrollment-confirm")).toBeDisabled();
});

test("aperçu : une erreur 404 affiche un message de ressource introuvable, pas 'Capacité insuffisante'", async ({ page, request }) => {
  await page.route("**/api/v1/students/bulk-enrollment*", async (route) => {
    if (route.request().url().includes("dry_run=true")) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Class not found" }) });
    } else {
      await route.continue();
    }
  });
  const { dialog, year, schoolClass } = await openPanelWithOneStudent(page, request, "previewnotfound");

  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });
  await dialog.getByLabel("Classe").selectOption({ label: schoolClass.name });

  const errorBlock = dialog.getByTestId("bulk-enrollment-preview-error");
  await expect(errorBlock).toContainText("Classe, année scolaire ou élève introuvable.");
  await expect(dialog.getByTestId("bulk-enrollment-capacity-error")).toHaveCount(0);
  await expect(dialog.getByTestId("bulk-enrollment-confirm")).toBeDisabled();
});

test("aperçu : une coupure réseau affiche un message réseau, pas 'Capacité insuffisante'", async ({ page, request }) => {
  await page.route("**/api/v1/students/bulk-enrollment*", async (route) => {
    if (route.request().url().includes("dry_run=true")) {
      await route.abort("failed");
    } else {
      await route.continue();
    }
  });
  const { dialog, year, schoolClass } = await openPanelWithOneStudent(page, request, "previewnetwork");

  await dialog.getByLabel("Année scolaire").selectOption({ label: year.name });
  await dialog.getByLabel("Classe").selectOption({ label: schoolClass.name });

  const errorBlock = dialog.getByTestId("bulk-enrollment-preview-error");
  await expect(errorBlock).toContainText("Impossible de calculer l'aperçu. Vérifiez votre connexion.");
  await expect(dialog.getByTestId("bulk-enrollment-capacity-error")).toHaveCount(0);
  await expect(dialog.getByTestId("bulk-enrollment-confirm")).toBeDisabled();
});

test("filtre Non affectés désactivé et message explicite sans année scolaire courante", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "noyearfilter");
  await api(request, admin.orgAdminToken, "POST", "/api/v1/academic-years", {
    school_id: admin.schoolId, name: "2026-2027", start_date: "2026-09-01", end_date: "2027-06-30", is_current: false,
  });
  await createStudent(request, admin, "NOYEAR-01", "SansAnnee");

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");

  await expect(page.getByTestId("no-current-year-notice")).toContainText("Aucune année scolaire courante définie.");
  await expect(page.getByRole("option", { name: "Non affectés" })).toBeDisabled();
  // La liste normale, elle, reste inchangée (tous les élèves visibles).
  await expect(page.locator("tbody tr", { hasText: "NOYEAR-01" })).toBeVisible();
});

test("fiche élève : panneau d'affectation en masse reste utilisable en mobile/tablette/desktop", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "bulkresponsive");
  await setupYearAndClass(request, admin, "CM1 A", 30);
  await createStudent(request, admin, "BE-030", "Responsive");

  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 820, height: 1180 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.locator("tbody tr", { hasText: "BE-030" }).getByRole("checkbox", { name: /Sélectionner/ }).check();
    await expect(page.getByRole("button", { name: "Affecter à une classe" })).toBeVisible();
    await page.locator("tbody tr", { hasText: "BE-030" }).getByRole("checkbox", { name: /Sélectionner/ }).uncheck();
  }
});
