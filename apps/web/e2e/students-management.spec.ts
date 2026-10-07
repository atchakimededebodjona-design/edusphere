import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, TENANT_PASSWORD, unique } from "./helpers/tenants";

// Gestion des élèves : affichage complet, tri par matricule, modification en masse après import.
// Toute la mise en place passe par l'API ; le navigateur ne fait que ce qu'un admin ferait.

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
  await page.getByPlaceholder("Mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");
}

test("liste des élèves : colonnes complètes, tri par matricule, sélection et modification en masse", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stue2e");

  const studentA = await api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId, matricule: "EL-CM1-010", first_name: "Koffi", last_name: "Mensah",
    date_of_birth: "2015-01-18", sex: "M",
  });
  const studentB = await api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId, matricule: "EL-CM1-002", first_name: "Afi", last_name: "Dogbe",
    date_of_birth: "2015-06-02", sex: "F",
  });
  await api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId, matricule: "EL-CM1-001", first_name: "Yao", last_name: "Agbo",
    date_of_birth: "2015-03-09", sex: "M",
  });

  await loginAdmin(page, admin.orgAdminEmail);
  await page.getByRole("link", { name: "Élèves" }).click();
  await expect(page).toHaveURL("/students");

  // En-têtes de colonnes complètes (plus de fusion prénom+nom).
  const table = page.getByRole("table");
  for (const header of ["Matricule", "Prénom", "Nom", "Date de naissance", "Sexe", "Statut", "Action"]) {
    await expect(table.getByRole("columnheader", { name: header, exact: true })).toBeVisible();
  }

  // Tri par matricule, cohérent (001, 002, 010 — jamais 010 avant 002).
  const matriculeCells = page.locator("tbody tr td:nth-child(2)");
  await expect(matriculeCells).toHaveText(["EL-CM1-001", "EL-CM1-002", "EL-CM1-010"]);

  // Prénom et nom dans des colonnes séparées, date au format FR, sexe lisible.
  const rowB = page.locator("tbody tr", { hasText: "EL-CM1-002" });
  await expect(rowB.getByText("Afi", { exact: true })).toBeVisible();
  await expect(rowB.getByText("Dogbe", { exact: true })).toBeVisible();
  await expect(rowB.getByText("02/06/2015")).toBeVisible();
  await expect(rowB.getByText("Féminin")).toBeVisible();

  // Sélection de deux élèves puis modification en masse du statut.
  await rowB.getByRole("checkbox", { name: /Sélectionner/ }).check();
  const rowC = page.locator("tbody tr", { hasText: "EL-CM1-001" });
  await rowC.getByRole("checkbox", { name: /Sélectionner/ }).check();
  await expect(page.getByText("2 élèves sélectionnés")).toBeVisible();

  await page.getByRole("button", { name: "Modifier en masse" }).click();
  await page.getByRole("dialog", { name: "Modifier en masse" }).getByLabel("Nouveau statut").selectOption("INACTIVE");
  await page.getByLabel("Motif du changement de statut").fill("Verification de rentree");
  await page.getByRole("button", { name: "Appliquer" }).click();

  // Le panneau se ferme, la sélection est vidée, les statuts sont à jour.
  await expect(page.getByRole("dialog", { name: "Modifier en masse" })).toHaveCount(0);
  await expect(page.getByText(/sélectionnés?/)).toHaveCount(0);
  await expect(rowB.getByText("Inactif")).toBeVisible();
  await expect(rowC.getByText("Inactif")).toBeVisible();
  // L'élève non sélectionné n'est pas affecté.
  await expect(page.locator("tbody tr", { hasText: "EL-CM1-010" }).getByText("Actif")).toBeVisible();

  // L'action "Modifier" ouvre bien la fiche existante.
  const rowA = page.locator("tbody tr", { hasText: "EL-CM1-010" });
  await rowA.getByRole("link", { name: "Modifier" }).click();
  await expect(page).toHaveURL(`/students/${studentA.id}`);
  await expect(page.getByRole("heading", { name: "Mensah Koffi" })).toBeVisible();
  await expect(page.getByText(`Matricule ${studentA.matricule}`)).toBeVisible();
});

test("import CSV : 15 élèves créés, 0 doublon, 0 erreur, note sur l'inscription", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuimport");
  await loginAdmin(page, admin.orgAdminEmail);
  await page.goto("/students");

  const prefix = unique("IMP").toUpperCase();
  const header = "matricule,first_name,last_name,date_of_birth,sex\n";
  const rows = Array.from({ length: 15 }, (_, i) => `${prefix}-${String(i + 1).padStart(3, "0")},Prenom${i},Nom${i},2014-0${(i % 9) + 1}-10,${i % 2 === 0 ? "F" : "M"}`);
  const csv = header + rows.join("\n") + "\n";

  await page.getByRole("button", { name: /Importer des élèves/ }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "eleves.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "utf-8") });
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page.getByText(/15 ligne\(s\)/)).toBeVisible();
  await expect(page.getByText("15 créé(s)", { exact: false })).toBeVisible();
  await expect(page.getByText("0 doublon(s) ignoré(s)", { exact: false })).toBeVisible();
  await expect(page.getByText("0 erreur(s)", { exact: false })).toBeVisible();
  await expect(page.getByText("ne sont pas automatiquement inscrits dans une classe")).toBeVisible();

  const check = await api(request, admin.orgAdminToken, "GET", `/api/v1/students?school_id=${admin.schoolId}&search=${prefix}`);
  expect(check).toHaveLength(15);
});

test("un enseignant pur n'atteint jamais la gestion admin des élèves (redirigé vers /teacher)", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuteacher");
  const teacherEmail = `${unique("prof").toLowerCase()}@wizard-e2e.example`;
  const created = await api(request, admin.orgAdminToken, "POST", "/api/v1/users", {
    email: teacherEmail, full_name: "Prof Eleves", school_id: admin.schoolId, role_code: "TEACHER",
  });
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: TENANT_PASSWORD },
  });

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(teacherEmail);
  await page.getByPlaceholder("Mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/teacher");

  // Accès direct par URL : aucune fonction de modification/masse n'est jamais vue.
  await page.goto("/students");
  await expect(page).toHaveURL("/teacher");
});
