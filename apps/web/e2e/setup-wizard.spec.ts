import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Assistant de mise en place académique (Phase 8). Exécuté contre l'API + Postgres réels
// (docker compose) — pas de mock, cohérent avec e2e/smoke.spec.ts. Chaque test crée sa propre
// école fraîche pour rester indépendant des autres runs, la base de test n'étant pas
// réinitialisée entre exécutions (cf. tests/conftest.py côté API).
//
// IMPORTANT — contournement d'un bug préexistant découvert pendant cette phase (documenté dans
// docs/phases/PHASE_8_IMPLEMENTATION.md, section "Discovered / Deferred") : l'admin créé par
// /register reçoit un rôle SCHOOL_ADMIN scopé ORGANISATION (school_id NULL, comportement backend
// intentionnel — un admin d'organisation gère toutes les écoles de son organisation). Mais
// `AuthProvider.tsx` (currentSchoolId) ne sait dériver l'école courante que d'un rôle scopé
// ÉCOLE explicite : pour cet admin fraîchement inscrit, currentSchoolId reste indéfiniment null
// et TOUTE page qui en dépend (dashboard, académique, et donc l'assistant) reste bloquée sur
// "Chargement...". Ce n'est pas un bug introduit par le wizard ni corrigé ici (Phase 8 ne doit
// pas modifier `auth`). Pour tester réellement le wizard, ces tests créent donc, via l'API,
// un second compte SCHOOL_ADMIN explicitement scopé à l'école (exactement le chemin déjà utilisé
// par la page "Utilisateurs" existante) et l'utilisent pour piloter l'interface.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";

function unique(prefix: string): string {
  return `${prefix}${Date.now()}${Math.floor(Math.random() * 10000)}`;
}

async function registerSchool(page: Page, request: APIRequestContext, slugPrefix: string) {
  const slug = unique(slugPrefix).toLowerCase();
  const orgAdminEmail = `${slug}-org@wizard-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Org Admin");
  await page.getByPlaceholder("Votre email").fill(orgAdminEmail);
  await page.getByPlaceholder("Mot de passe (8 caractères min.)").fill(password);
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL("/");

  // L'admin d'organisation ci-dessus a un rôle scopé organisation (currentSchoolId cassé, voir
  // le commentaire en tête de fichier) : on récupère son token pour créer, via l'API, un second
  // compte explicitement scopé école — le chemin réellement utilisable pour piloter le wizard.
  const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, {
    data: { email: orgAdminEmail, password },
  });
  const { access_token: orgAdminToken } = await loginResponse.json();

  const meResponse = await request.get(`${API_BASE_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${orgAdminToken}` },
  });
  const me = await meResponse.json();
  const orgId: string = me.roles[0].organization_id;

  const schoolsResponse = await request.get(`${API_BASE_URL}/api/v1/schools?organization_id=${orgId}`, {
    headers: { Authorization: `Bearer ${orgAdminToken}` },
  });
  const schools = await schoolsResponse.json();
  const schoolId: string = schools[0].id;

  const schoolAdminEmail = `${slug}-admin@wizard-e2e.example`;
  const createUserResponse = await request.post(`${API_BASE_URL}/api/v1/users`, {
    headers: { Authorization: `Bearer ${orgAdminToken}` },
    data: { email: schoolAdminEmail, full_name: "Admin Test", school_id: schoolId, role_code: "SCHOOL_ADMIN" },
  });
  const created = await createUserResponse.json();
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: password },
  });

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(schoolAdminEmail);
  await page.getByPlaceholder("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/");

  return { slug, email: schoolAdminEmail, password, schoolId, orgAdminToken };
}

test.describe("Assistant de mise en place — parcours complet", () => {
  test("un admin peut configurer une école neuve de bout en bout (accès, création, navigation, résumé)", async ({
    page,
    request,
  }) => {
    await registerSchool(page, request, "wizhappy");

    // 1. Accès autorisé (nav + page)
    await page.getByRole("link", { name: "Mise en place" }).click();
    await expect(page).toHaveURL("/setup");
    await expect(page.getByRole("heading", { name: "Mise en place de l'école" })).toBeVisible();

    // Étape 1 — Année scolaire (aucune ne préexiste : pas de fieldset "Années existantes")
    await expect(page.getByRole("heading", { name: "Année scolaire" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continuer" })).toBeDisabled();
    const yearName = unique("Annee-");
    await page.getByPlaceholder("2026-2027").fill(yearName);
    await page.getByLabel("Début").fill("2026-09-01");
    await page.getByLabel("Fin").fill("2027-06-30");
    await page.getByRole("button", { name: "Créer cette année" }).click();
    await expect(page.getByText(yearName)).toBeVisible();

    // La sélection auto de l'année créée débloque "Continuer".
    await expect(page.getByRole("button", { name: "Continuer" })).toBeEnabled();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 2 — Termes
    await expect(page.getByRole("heading", { name: "Termes / périodes" })).toBeVisible();
    await expect(page.getByText("Aucun terme pour cette année")).toBeVisible();
    await page.getByPlaceholder("Trimestre 1").fill("Trimestre 1");
    await page.locator('input[type="date"]').nth(0).fill("2026-09-01");
    await page.locator('input[type="date"]').nth(1).fill("2026-12-20");
    await page.getByRole("button", { name: "Ajouter ce terme" }).click();
    await expect(page.getByText("Trimestre 1 (2026-09-01")).toBeVisible();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 3 — Niveaux
    await expect(page.getByRole("heading", { name: "Niveaux", exact: true })).toBeVisible();
    await page.getByPlaceholder("CE1").fill("CE1");
    await page.getByRole("button", { name: "Ajouter ce niveau" }).click();
    await expect(page.getByText("CE1", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 4 — Matières
    await expect(page.getByRole("heading", { name: "Matières" })).toBeVisible();
    await page.getByPlaceholder("Mathématiques").fill("Mathématiques");
    await page.getByRole("button", { name: "Ajouter cette matière" }).click();
    await expect(page.getByText("Mathématiques", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 5 — Classes
    await expect(page.getByRole("heading", { name: "Classes" })).toBeVisible();
    await page.getByPlaceholder("CE1-A").fill("CE1-A");
    await page.getByLabel("Niveau").selectOption({ label: "CE1" });
    await page.getByRole("button", { name: "Ajouter cette classe" }).click();
    await expect(page.getByText("CE1-A — CE1")).toBeVisible();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 6 — Affectations enseignants (attache la matière à la classe)
    await expect(page.getByRole("heading", { name: "Affectations enseignants" })).toBeVisible();
    await page.getByLabel("Classe").selectOption({ label: "CE1-A" });
    await page.getByLabel("Matière").selectOption({ label: "Mathématiques" });
    await page.getByRole("button", { name: "Ajouter" }).click();
    await expect(page.getByText("Mathématiques — coefficient 1")).toBeVisible();
    await page.getByRole("button", { name: "Continuer" }).click();

    // Étape 7 — Résumé
    await expect(page.getByRole("heading", { name: "Résumé et confirmation" })).toBeVisible();
    await expect(page.getByText(`Configuration de l'école — ${yearName}`)).toBeVisible();
    await expect(page.getByText("Termes : 1")).toBeVisible();
    await expect(page.getByText("Niveaux : 1")).toBeVisible();
    await expect(page.getByText("Matières : 1")).toBeVisible();
    await expect(page.getByText("Classes (cette année) : 1")).toBeVisible();

    // Navigation "Précédent" : retour possible sans perte de données déjà enregistrées.
    await page.getByRole("button", { name: "Précédent" }).click();
    await expect(page.getByRole("heading", { name: "Affectations enseignants" })).toBeVisible();
    await page.getByLabel("Classe").selectOption({ label: "CE1-A" });
    await expect(page.getByText("Mathématiques — coefficient 1")).toBeVisible();
  });

  test("les données déjà configurées sont chargées et réutilisables au rechargement (pas de doublon)", async ({
    page,
    request,
  }) => {
    await registerSchool(page, request, "wizreload");
    await page.goto("/setup");

    const yearName = unique("Annee-");
    await page.getByPlaceholder("2026-2027").fill(yearName);
    await page.getByLabel("Début").fill("2026-09-01");
    await page.getByLabel("Fin").fill("2027-06-30");
    await page.getByRole("button", { name: "Créer cette année" }).click();
    await expect(page.getByText(yearName)).toBeVisible();

    // Rechargement complet de la page : l'année créée doit réapparaître comme sélectionnable,
    // pas être recréée.
    await page.reload();
    await expect(page.getByRole("radio", { name: new RegExp(yearName) })).toBeVisible();
    const yearOccurrences = await page.getByText(yearName).count();
    expect(yearOccurrences).toBe(1);

    // La sélectionner ne recrée rien côté serveur : "Continuer" se débloque directement.
    await page.getByRole("radio", { name: new RegExp(yearName) }).check();
    await expect(page.getByRole("button", { name: "Continuer" })).toBeEnabled();
  });

  test("empêche les doublons et affiche une erreur compréhensible (pas de stack trace)", async ({ page, request }) => {
    await registerSchool(page, request, "wizdupe");
    await page.goto("/setup");

    const yearName = unique("Annee-");
    await page.getByPlaceholder("2026-2027").fill(yearName);
    await page.getByLabel("Début").fill("2026-09-01");
    await page.getByLabel("Fin").fill("2027-06-30");
    await page.getByRole("button", { name: "Créer cette année" }).click();
    await expect(page.getByText(yearName)).toBeVisible();

    // Recréer une année avec le même nom -> conflit serveur (409), message clair, pas de doublon
    // affiché dans la liste.
    await page.getByPlaceholder("2026-2027").fill(yearName);
    await page.getByLabel("Début").fill("2026-09-01");
    await page.getByLabel("Fin").fill("2027-06-30");
    await page.getByRole("button", { name: "Créer cette année" }).click();

    // Note : getByRole("alert") remonterait aussi le route-announcer interne de Next.js
    // (#__next-route-announcer__, role="alert" lui aussi) — on cible donc le texte exact.
    const wizardAlert = page.getByText("Cet élément existe déjà.", { exact: true });
    await expect(wizardAlert).toBeVisible();
    await expect(wizardAlert).not.toContainText("Traceback");
    await expect(wizardAlert).not.toContainText("File \"");
    expect(await page.getByText(yearName).count()).toBe(1);
  });

  test("session expirée : message clair et action de reconnexion, pas de plantage", async ({ page, request }) => {
    await registerSchool(page, request, "wizsession");
    await page.goto("/setup");

    // On attend que le chargement initial réussisse (jetons valides) avant de corrompre la
    // session, pour simuler une expiration EN COURS D'UTILISATION plutôt qu'une session déjà
    // morte au chargement (ce second cas est couvert ailleurs par AuthGate : redirection vers
    // /login, comportement différent et déjà existant, pas testé ici).
    await expect(page.getByPlaceholder("2026-2027")).toBeVisible();

    // Corrompt les deux jetons stockés : la prochaine requête échoue en 401, le rafraîchissement
    // silencieux échoue aussi (refresh_token invalide) -> apiFetch nettoie la session et relève
    // l'erreur 401 d'origine, exactement le chemin réel emprunté par une vraie expiration.
    await page.evaluate(() => {
      window.localStorage.setItem(
        "edusphere.session",
        JSON.stringify({ access_token: "invalid.token.value", refresh_token: "invalid.refresh.value" }),
      );
    });

    await page.getByPlaceholder("2026-2027").fill(unique("Annee-"));
    await page.getByLabel("Début").fill("2026-09-01");
    await page.getByLabel("Fin").fill("2027-06-30");
    await page.getByRole("button", { name: "Créer cette année" }).click();

    await expect(page.getByText("Votre session a expiré. Reconnectez-vous pour continuer.", { exact: true })).toBeVisible();
  });
});

test("un enseignant (sans permission académique) n'a pas accès à l'assistant", async ({ page, request }) => {
  const { slug, orgAdminToken, schoolId } = await registerSchool(page, request, "wizrbac");

  const teacherEmail = `${slug}-teacher@wizard-e2e.example`;
  const createUserResponse = await request.post(`${API_BASE_URL}/api/v1/users`, {
    headers: { Authorization: `Bearer ${orgAdminToken}` },
    data: { email: teacherEmail, full_name: "Prof Test", school_id: schoolId, role_code: "TEACHER" },
  });
  const created = await createUserResponse.json();

  const teacherPassword = "TeacherPass123";
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: teacherPassword },
  });

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(teacherEmail);
  await page.getByPlaceholder("Mot de passe").fill(teacherPassword);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/");

  // Le lien "Mise en place" n'apparaît pas dans la navigation pour un enseignant...
  await expect(page.getByRole("link", { name: "Mise en place" })).toHaveCount(0);

  // ...et un accès direct par URL affiche un refus clair plutôt que l'assistant.
  await page.goto("/setup");
  await expect(page.getByText("Vous n'avez pas la permission d'accéder à cette page.", { exact: true })).toBeVisible();
});

test("isolation tenant : les années d'une école n'apparaissent pas dans l'assistant d'une autre école", async ({
  page,
  request,
  browser,
}) => {
  const schoolAYear = unique("Annee-SeulA-");

  await registerSchool(page, request, "wiztenanta");
  await page.goto("/setup");
  await page.getByPlaceholder("2026-2027").fill(schoolAYear);
  await page.getByLabel("Début").fill("2026-09-01");
  await page.getByLabel("Fin").fill("2027-06-30");
  await page.getByRole("button", { name: "Créer cette année" }).click();
  await expect(page.getByText(schoolAYear)).toBeVisible();

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  await registerSchool(pageB, contextB.request, "wiztenantb");
  await pageB.goto("/setup");

  await expect(pageB.getByText(schoolAYear)).toHaveCount(0);
  await expect(pageB.getByText("Années existantes")).toHaveCount(0);

  await contextB.close();
});
