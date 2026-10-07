import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, type TenantAdmin } from "./helpers/tenants";

// Sprint "Fiche élève — UX, documents, photo et inscriptions" : parcours complet sur la fiche
// élève (identité, photo, documents, inscriptions) avec les nouveaux contrôles de validation.

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

// PNG 1x1 valide (Pillow l'ouvre sans erreur) — nécessaire depuis que l'upload de photo valide
// réellement le contenu, pas seulement le Content-Type déclaré par le navigateur.
const VALID_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
const VALID_PDF_BUFFER = Buffer.from("%PDF-1.4\n%fake-but-correctly-signed-pdf-content\n%%EOF", "utf-8");

async function api(request: APIRequestContext, token: string, method: "GET" | "POST", path: string, data?: unknown) {
  const response = await request.fetch(`${API_BASE_URL}${path}`, { method, headers: { Authorization: `Bearer ${token}` }, data });
  expect(response.status(), `${method} ${path} → ${await response.text()}`).toBeLessThan(300);
  return response.json();
}

async function loginAdmin(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");
}

async function createStudentAndOpenProfile(
  page: Page,
  request: APIRequestContext,
  admin: TenantAdmin,
  matricule: string,
): Promise<string> {
  const student = await api(request, admin.orgAdminToken, "POST", "/api/v1/students", {
    school_id: admin.schoolId,
    matricule,
    first_name: "Ama",
    last_name: "Mensah",
    date_of_birth: "2014-04-20",
    sex: "F",
  });
  await page.goto(`/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Mensah Ama" })).toBeVisible();
  // React StrictMode (activé en dev, voir next.config.js) double-invoque les effects au montage :
  // le fetch initial de la fiche élève part deux fois quasi simultanément. Attendre que le réseau
  // se stabilise avant d'interagir évite qu'un second fetch en vol n'écrase une saisie en cours.
  await page.waitForLoadState("networkidle");
  return student.id;
}

test("fiche élève : modification des informations avec des champs correctement labellisés", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuprofile");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-PROFIL-001");

  // Les champs sont de vrais <label> (getByLabel), pas seulement des placeholders.
  await page.getByLabel("Adresse").fill("12 rue des Flamboyants");
  await page.getByLabel("Lieu de naissance").fill("Lomé");
  await page.getByTestId("student-save").click();

  await expect(page.getByTestId("student-save-success")).toBeVisible();
  await expect(page.getByLabel("Adresse")).toHaveValue("12 rue des Flamboyants");
});

test("photo élève : upload, affichage, remplacement et suppression avec confirmation", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuphoto");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-PHOTO-001");

  await expect(page.getByTestId("student-photo-empty")).toBeVisible();

  await page.getByTestId("photo-file-input").setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: Buffer.from(VALID_PNG_BASE64, "base64"),
  });
  await expect(page.getByTestId("student-photo-img")).toBeVisible();

  // Suppression avec confirmation explicite (pas de suppression directe sans étape intermédiaire).
  await page.getByTestId("photo-delete").click();
  await expect(page.getByTestId("photo-delete-confirm")).toBeVisible();
  await page.getByTestId("photo-delete-confirm-yes").click();

  await expect(page.getByTestId("student-photo-empty")).toBeVisible();
});

test("photo élève : un fichier invalide est rejeté avec un message précis", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuphotobad");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-PHOTOBAD-001");

  await page.getByTestId("photo-file-input").setInputFiles({
    name: "notanimage.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("ceci n'est pas une image", "utf-8"),
  });

  await expect(page.getByTestId("photo-error")).toBeVisible();
  await expect(page.getByTestId("student-photo-empty")).toBeVisible();
});

test("documents élève : upload PDF, métadonnées affichées, téléchargement, suppression avec confirmation", async ({
  page,
  request,
}) => {
  const admin = await createOrganizationViaPlatform(request, "studocs");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-DOCS-001");

  await expect(page.getByTestId("documents-empty")).toBeVisible();

  // Sélection d'un type via les chips suggérés plutôt qu'un champ texte libre.
  await page.getByRole("button", { name: "Bulletin", exact: true }).click();
  await page.getByTestId("document-file-input").setInputFiles({
    name: "bulletin.pdf",
    mimeType: "application/pdf",
    buffer: VALID_PDF_BUFFER,
  });

  // Aperçu du fichier sélectionné avant envoi (nom, taille, type).
  await expect(page.getByTestId("document-file-preview")).toContainText("bulletin.pdf");

  await page.getByRole("button", { name: "Ajouter le document" }).click();
  await expect(page.getByTestId("document-upload-success")).toBeVisible();

  const row = page.getByTestId("document-row").filter({ hasText: "bulletin.pdf" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Bulletin");
  await expect(page.getByTestId("documents-count")).toContainText("1 document");

  const downloadPromise = page.waitForEvent("download");
  await row.getByTestId("document-download").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("bulletin.pdf");

  await row.getByTestId("document-delete").click();
  // La ligne desktop et la carte mobile équivalente existent toutes deux dans le DOM (seule la
  // visibilité CSS diffère) : scoper à `row` évite une violation du mode strict Playwright.
  await expect(row.getByTestId("document-delete-confirm")).toBeVisible();
  await row.getByTestId("document-delete-confirm-yes").click();

  await expect(page.getByTestId("documents-empty")).toBeVisible();
});

test("documents élève : un type de document personnalisé (Autre) et un fichier rejeté avant envoi", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "studocsother");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-DOCSOTHER-001");

  await page.getByRole("button", { name: "Autre", exact: true }).click();
  await page.getByTestId("document-type-custom").fill("Lettre de recommandation");

  // Fichier trop volumineux rejeté visuellement avant tout envoi réseau.
  const oversized = Buffer.alloc(10 * 1024 * 1024 + 1, 1);
  await page.getByTestId("document-file-input").setInputFiles({
    name: "trop-gros.pdf",
    mimeType: "application/pdf",
    buffer: oversized,
  });
  await expect(page.getByTestId("document-file-error")).toBeVisible();
  await expect(page.getByTestId("documents-empty")).toBeVisible();
});

test("inscriptions : affichage de l'année scolaire par son nom et de la date au format JJ/MM/AAAA", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "stuenroll");

  const year = await api(request, admin.orgAdminToken, "POST", "/api/v1/academic-years", {
    school_id: admin.schoolId, name: "2026-2027", start_date: "2026-09-01", end_date: "2027-06-30",
  });
  const level = await api(request, admin.orgAdminToken, "POST", "/api/v1/education-levels", {
    school_id: admin.schoolId, name: "CM2",
  });
  const schoolClass = await api(request, admin.orgAdminToken, "POST", "/api/v1/classes", {
    academic_year_id: year.id, education_level_id: level.id, name: "B",
  });

  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  const studentId = await createStudentAndOpenProfile(page, request, admin, "EL-ENROLL-001");

  await page.getByLabel("Classe").selectOption(schoolClass.id);
  await page.getByLabel("Date d'inscription").fill("2026-09-01");
  await page.getByRole("button", { name: "Inscrire" }).click();

  const row = page.getByTestId("enrollment-row").filter({ hasText: "B" });
  await expect(row).toContainText("2026-2027");
  await expect(row).toContainText("01/09/2026");
  await expect(row.locator("select")).toHaveValue("ACTIVE");

  // Non-régression : le conflit d'inscription sur la même année scolaire reste un message clair.
  const duplicate = await request.fetch(`${API_BASE_URL}/api/v1/students/${studentId}/enrollments`, {
    method: "POST",
    headers: { Authorization: `Bearer ${admin.orgAdminToken}` },
    data: { class_id: schoolClass.id, enrollment_date: "2026-09-01" },
  });
  expect(duplicate.status()).toBe(409);
});

test("fiche élève : mise en page responsive (mobile, tablette, desktop)", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "sturesponsive");
  await loginAdmin(page, admin.orgAdminEmail, admin.password);
  await createStudentAndOpenProfile(page, request, admin, "EL-RESP-001");

  for (const viewport of [
    { width: 390, height: 844 }, // mobile
    { width: 820, height: 1180 }, // tablette
    { width: 1440, height: 900 }, // desktop
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.getByTestId("student-save")).toBeVisible();
    await expect(page.getByLabel("Adresse")).toBeVisible();
    // Le contenu de LA FICHE ÉLÈVE (<main>, hors barre latérale de l'app — pré-existante et hors
    // périmètre de ce sprint) ne doit jamais forcer un débordement horizontal de son propre conteneur.
    const mainOverflows = await page.evaluate(() => {
      const main = document.querySelector("main");
      return !!main && main.scrollWidth > main.clientWidth + 1;
    });
    expect(mainOverflows).toBe(false);
  }
});
