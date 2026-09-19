import { expect, test, type APIRequestContext } from "@playwright/test";

// Phase 28A — Portail Parent Web. Exécuté contre l'API + Postgres réels, sans mock. Le contexte
// élève/notes/présence/bulletin/frais est construit directement via l'API (comme
// apps/api/tests/test_parent.py::_setup_child_context), seule la partie réellement testée
// (connexion + navigation du portail parent) passe par l'UI.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const PARENT_PASSWORD = "ParentPass123";

function unique(prefix: string): string {
  return `${prefix}${Date.now()}${Math.floor(Math.random() * 10000)}`;
}

// À la différence de apps/web/e2e/dashboard.spec.ts::registerSchool (qui passe par la page
// /register), la création d'organisation/école/admin se fait ici en API directe : une régression
// pré-existante et hors périmètre de cette phase (bug confirmé indépendant de Phase 28A — reproduit
// à l'identique sur dashboard.spec.ts non modifié, avec ou sans les changements de cette phase,
// via `git stash`) bloque actuellement le flux register->login de la page /register elle-même dans
// cet environnement. Ce test vise le portail PARENT, pas cette page : passer par l'API pour la
// seule mise en place évite de dépendre d'un chemin déjà cassé avant même Phase 28A, sans le
// masquer ni le corriger (voir le rapport final pour le signalement complet).
async function registerSchool(request: APIRequestContext, slugPrefix: string) {
  const slug = unique(slugPrefix).toLowerCase();
  const orgAdminEmail = `${slug}-org@wizard-e2e.example`;
  const password = "SuperSecret123";

  const registerResponse = await request.post(`${API_BASE_URL}/api/v1/auth/register`, {
    data: {
      organization_name: `Org ${slug}`,
      organization_slug: slug,
      country_code: "TG",
      school_name: `Ecole ${slug}`,
      school_slug: slug,
      admin_full_name: "Org Admin",
      admin_email: orgAdminEmail,
      admin_password: password,
    },
  });
  const registered = await registerResponse.json();
  const orgAdminToken: string = registered.tokens.access_token;
  const schoolId: string = registered.school.id;

  return { slug, schoolId, orgAdminHeaders: { Authorization: `Bearer ${orgAdminToken}` } };
}

async function apiHeaders(request: APIRequestContext, email: string, password: string) {
  const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
  const { access_token } = await loginResponse.json();
  return { Authorization: `Bearer ${access_token}` };
}

// Construit un contexte complet pour UN enfant : classe/matière/évaluation notée, session de
// présence, bulletin publié, frais avec un paiement — le minimum pour exercer les 4 onglets du
// portail parent (Présence/Notes/Bulletins/Frais), puis lie un compte PARENT à cet enfant via un
// Guardian — mêmes étapes que test_parent.py::_setup_linked_parent, en TypeScript.
async function setupLinkedParent(
  request: APIRequestContext,
  headers: Record<string, string>,
  schoolId: string,
  slug: string,
) {
  const today = new Date().toISOString().slice(0, 10);
  const minus30 = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const in180 = new Date(Date.now() + 180 * 86400000).toISOString().slice(0, 10);

  const year = await (
    await request.post(`${API_BASE_URL}/api/v1/academic-years`, {
      headers,
      data: { school_id: schoolId, name: `Annee-${slug}`, start_date: minus30, end_date: in180 },
    })
  ).json();
  const term = await (
    await request.post(`${API_BASE_URL}/api/v1/academic-terms`, {
      headers,
      data: { academic_year_id: year.id, name: `Terme-${slug}`, start_date: minus30, end_date: in180 },
    })
  ).json();
  const level = await (
    await request.post(`${API_BASE_URL}/api/v1/education-levels`, { headers, data: { school_id: schoolId, name: `CE1-${slug}` } })
  ).json();
  const schoolClass = await (
    await request.post(`${API_BASE_URL}/api/v1/classes`, {
      headers,
      data: { academic_year_id: year.id, education_level_id: level.id, name: "A" },
    })
  ).json();
  const subject = await (
    await request.post(`${API_BASE_URL}/api/v1/subjects`, { headers, data: { school_id: schoolId, name: `Maths-${slug}` } })
  ).json();
  const classSubject = await (
    await request.post(`${API_BASE_URL}/api/v1/classes/${schoolClass.id}/subjects`, {
      headers,
      data: { subject_id: subject.id, coefficient: 1 },
    })
  ).json();
  const assessmentType = await (
    await request.post(`${API_BASE_URL}/api/v1/assessment-types`, { headers, data: { school_id: schoolId, name: `Devoir-${slug}` } })
  ).json();

  const student = await (
    await request.post(`${API_BASE_URL}/api/v1/students`, {
      headers,
      data: {
        school_id: schoolId,
        matricule: `P${slug}`,
        first_name: "Kofi",
        last_name: "Enfant",
        date_of_birth: "2015-01-01",
        sex: "M",
      },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/students/${student.id}/enrollments`, {
    headers,
    data: { class_id: schoolClass.id, enrollment_date: minus30 },
  });

  const assessment = await (
    await request.post(`${API_BASE_URL}/api/v1/assessments`, {
      headers,
      data: {
        class_subject_id: classSubject.id,
        academic_term_id: term.id,
        assessment_type_id: assessmentType.id,
        name: "Devoir 1",
        assessment_date: today,
      },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/results`, {
    headers,
    data: { assessment_id: assessment.id, results: [{ student_id: student.id, score: 15 }] },
  });

  const session = await (
    await request.post(`${API_BASE_URL}/api/v1/attendance-sessions`, {
      headers,
      data: { class_id: schoolClass.id, academic_term_id: term.id, session_date: today },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/attendance-records`, {
    headers,
    data: { session_id: session.id, records: [{ student_id: student.id, status: "PRESENT" }] },
  });

  const template = await (
    await request.post(`${API_BASE_URL}/api/v1/report-card-templates`, {
      headers,
      data: { school_id: schoolId, name: `Standard-${slug}`, html_content: "<html><body><p>{{ student.first_name }}</p></body></html>" },
    })
  ).json();
  const generated = await (
    await request.post(`${API_BASE_URL}/api/v1/report-cards/generate`, {
      headers,
      data: { class_id: schoolClass.id, academic_term_id: term.id, template_id: template.id },
    })
  ).json();
  const reportCard = generated[0];
  await request.post(`${API_BASE_URL}/api/v1/report-cards/${reportCard.id}/publish`, { headers });

  const category = await (
    await request.post(`${API_BASE_URL}/api/v1/fee-categories`, { headers, data: { school_id: schoolId, name: `Scolarite-${slug}` } })
  ).json();
  const schedule = await (
    await request.post(`${API_BASE_URL}/api/v1/fee-schedules`, {
      headers,
      data: {
        school_id: schoolId,
        fee_category_id: category.id,
        academic_year_id: year.id,
        name: `Frais-${slug}`,
        amount: "10000",
        scope_type: "SCHOOL",
      },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/fee-schedules/${schedule.id}/generate`, { headers });
  const summary = await (
    await request.get(`${API_BASE_URL}/api/v1/students/${student.id}/financial-summary`, { headers })
  ).json();
  const studentFeeId: string = summary.fees[0].id;
  await request.post(`${API_BASE_URL}/api/v1/payments`, {
    headers,
    data: {
      student_id: student.id,
      amount: "5000",
      method: "CASH",
      paid_at: today,
      idempotency_key: unique("idem"),
      allocations: [{ student_fee_id: studentFeeId, amount: "5000" }],
    },
  });

  // Compte PARENT + Guardian lié — même mécanisme que test_parent.py::_setup_linked_parent.
  const email = `${unique(`parent-${slug}`)}@wizard-e2e.example`.toLowerCase();
  const createUser = await (
    await request.post(`${API_BASE_URL}/api/v1/users`, {
      headers,
      data: { email, full_name: "Parent Test", school_id: schoolId, role_code: "PARENT" },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: createUser.dev_reset_token, new_password: PARENT_PASSWORD },
  });
  const guardian = await (
    await request.post(`${API_BASE_URL}/api/v1/guardians`, {
      headers,
      data: { school_id: schoolId, full_name: "Tuteur Test", relationship_type: "father" },
    })
  ).json();
  await request.patch(`${API_BASE_URL}/api/v1/guardians/${guardian.id}`, {
    headers,
    data: { user_id: createUser.user.id },
  });
  await request.post(`${API_BASE_URL}/api/v1/students/${student.id}/guardians`, {
    headers,
    data: { guardian_id: guardian.id },
  });

  return { student, parentEmail: email };
}

test("portail parent : connexion, tableau de bord, présence, notes, bulletin et frais d'un enfant", async ({ page, request }) => {
  const { schoolId, orgAdminHeaders } = await registerSchool(request, "parentportal");
  const { student, parentEmail } = await setupLinkedParent(request, orgAdminHeaders, schoolId, "main");

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(parentEmail);
  await page.getByPlaceholder("Mot de passe").fill(PARENT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();

  // Un compte PARENT est redirigé vers son propre portail, jamais vers le tableau de bord admin.
  await expect(page).toHaveURL("/parent");
  await expect(page.getByText("1 enfant est rattaché à votre compte.")).toBeVisible();
  await expect(page.getByText("Kofi Enfant")).toBeVisible();

  await page.getByRole("link", { name: "Mes enfants" }).click();
  await expect(page).toHaveURL("/parent/children");
  await expect(page.getByText(`Matricule ${student.matricule}`)).toBeVisible();

  await page.getByRole("link", { name: /Kofi Enfant/ }).click();
  await expect(page).toHaveURL(`/parent/children/${student.id}`);
  await expect(page.getByRole("heading", { name: "Kofi Enfant" })).toBeVisible();

  // Onglet Présence (actif par défaut).
  await expect(page.getByText("Présences", { exact: true })).toBeVisible();
  await expect(page.getByText("1", { exact: true }).first()).toBeVisible();

  // Onglet Notes (moyenne de matière ET moyenne générale valent toutes deux 15.00 ici — une
  // seule matière notée — d'où le premier élément plutôt qu'un texte supposé unique).
  await page.getByRole("button", { name: "Notes" }).click();
  await expect(page.getByText("15.00").first()).toBeVisible();

  // Onglet Bulletins.
  await page.getByRole("button", { name: "Bulletins" }).click();
  await expect(page.getByText(/Moyenne générale/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Télécharger le PDF" })).toBeVisible();

  // Onglet Frais (le montant dû apparaît à la fois dans le résumé et dans la ligne du tableau).
  await page.getByRole("button", { name: "Frais" }).click();
  await expect(page.getByText("10000").first()).toBeVisible(); // total dû
  await expect(page.getByText("5000").first()).toBeVisible(); // total payé / montant du paiement
  await expect(page.getByRole("button", { name: "Reçu" })).toBeVisible();
});

test("portail parent : isolation stricte — un parent ne voit jamais les données d'un autre parent", async ({ page, request }) => {
  const { schoolId, orgAdminHeaders } = await registerSchool(request, "parentisolation");
  const a = await setupLinkedParent(request, orgAdminHeaders, schoolId, "a");
  const b = await setupLinkedParent(request, orgAdminHeaders, schoolId, "b");

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(a.parentEmail);
  await page.getByPlaceholder("Mot de passe").fill(PARENT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/parent");

  // La liste "Mes enfants" du parent A ne contient jamais l'enfant du parent B.
  await page.goto("/parent/children");
  await expect(page.getByText(`Matricule ${a.student.matricule}`)).toBeVisible();
  await expect(page.getByText(`Matricule ${b.student.matricule}`)).toHaveCount(0);

  // Navigation directe (URL tapée/devinée) vers l'enfant du parent B : jamais de données, jamais
  // une preuve d'autorisation tirée du seul id dans l'URL (voir parent/children/[id]/page.tsx).
  await page.goto(`/parent/children/${b.student.id}`);
  await expect(page.getByText("n'est pas rattaché à votre compte")).toBeVisible();

  // Vérification directe côté API avec le token du parent A : chaque endpoint /parent/* revalide
  // indépendamment (défense en profondeur, pas seulement l'écran ci-dessus).
  const headersA = await apiHeaders(request, a.parentEmail, PARENT_PASSWORD);
  const forged = await request.get(`${API_BASE_URL}/api/v1/parent/children/${b.student.id}/fees`, { headers: headersA });
  expect(forged.status()).toBe(404);
});
