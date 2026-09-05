import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Phase 10 — tableau de bord opérationnel admin. Exécuté contre l'API + Postgres réels, sans
// mock. Les métriques exactes attendues ici sont les mêmes que celles vérifiées côté backend
// dans apps/api/tests/test_dashboard.py (1 présent/1 absent -> 50%, 1 résultat saisi sur 2
// attendus -> 50%, 1 bulletin publié sur 2 générés).
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

  // Contournement du bug d'onboarding organisationnel documenté en Phase 8.1 (currentSchoolId) :
  // même mécanisme que setup-wizard.spec.ts / admin-onboarding.spec.ts — un second compte admin
  // explicitement scopé école, seul chemin qui pilote réellement l'interface web.
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
  const schoolId: string = (await schoolsResponse.json())[0].id;

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

async function apiHeaders(request: APIRequestContext, email: string, password: string) {
  const loginResponse = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password } });
  const { access_token } = await loginResponse.json();
  return { Authorization: `Bearer ${access_token}` };
}

test("tableau de bord : métriques réelles pour une école peuplée", async ({ page, request }) => {
  const { email, password, schoolId } = await registerSchool(page, request, "dashfull");
  const headers = await apiHeaders(request, email, password);
  const today = new Date().toISOString().slice(0, 10);
  const in30 = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
  const minus30 = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const minus180 = new Date(Date.now() - 180 * 86400000).toISOString().slice(0, 10);
  const plus180 = new Date(Date.now() + 180 * 86400000).toISOString().slice(0, 10);

  const year = await (
    await request.post(`${API_BASE_URL}/api/v1/academic-years`, {
      headers,
      data: { school_id: schoolId, name: "Annee-E2E", start_date: minus180, end_date: plus180, is_current: true },
    })
  ).json();
  const term = await (
    await request.post(`${API_BASE_URL}/api/v1/academic-terms`, {
      headers,
      data: { academic_year_id: year.id, name: "Terme-E2E", start_date: minus30, end_date: in30 },
    })
  ).json();
  const level = await (
    await request.post(`${API_BASE_URL}/api/v1/education-levels`, { headers, data: { school_id: schoolId, name: "CE1" } })
  ).json();
  const schoolClass = await (
    await request.post(`${API_BASE_URL}/api/v1/classes`, {
      headers,
      data: { academic_year_id: year.id, education_level_id: level.id, name: "A" },
    })
  ).json();
  const subject = await (
    await request.post(`${API_BASE_URL}/api/v1/subjects`, { headers, data: { school_id: schoolId, name: "Maths" } })
  ).json();
  const classSubject = await (
    await request.post(`${API_BASE_URL}/api/v1/classes/${schoolClass.id}/subjects`, {
      headers,
      data: { subject_id: subject.id, coefficient: 1 },
    })
  ).json();

  const students = [];
  for (let i = 0; i < 2; i++) {
    const student = await (
      await request.post(`${API_BASE_URL}/api/v1/students`, {
        headers,
        data: {
          school_id: schoolId,
          matricule: `E2E${i}`,
          first_name: `Eleve${i}`,
          last_name: "Dash",
          date_of_birth: "2015-01-01",
          sex: "F",
        },
      })
    ).json();
    await request.post(`${API_BASE_URL}/api/v1/students/${student.id}/enrollments`, {
      headers,
      data: { class_id: schoolClass.id, enrollment_date: minus30 },
    });
    students.push(student);
  }

  const session = await (
    await request.post(`${API_BASE_URL}/api/v1/attendance-sessions`, {
      headers,
      data: { class_id: schoolClass.id, academic_term_id: term.id, session_date: today },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/attendance-records`, {
    headers,
    data: {
      session_id: session.id,
      records: [
        { student_id: students[0].id, status: "PRESENT" },
        { student_id: students[1].id, status: "ABSENT" },
      ],
    },
  });

  const assessmentType = await (
    await request.post(`${API_BASE_URL}/api/v1/assessment-types`, { headers, data: { school_id: schoolId, name: "Devoir" } })
  ).json();
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
    data: { assessment_id: assessment.id, results: [{ student_id: students[0].id, score: 15 }] },
  });

  const template = await (
    await request.post(`${API_BASE_URL}/api/v1/report-card-templates`, {
      headers,
      data: { school_id: schoolId, name: "Standard", html_content: "<p>{{ student.first_name }}</p>" },
    })
  ).json();
  const generated = await (
    await request.post(`${API_BASE_URL}/api/v1/report-cards/generate`, {
      headers,
      data: { class_id: schoolClass.id, academic_term_id: term.id, template_id: template.id },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/report-cards/${generated[0].id}/publish`, { headers });

  await page.goto("/");
  await expect(page.getByText("Chargement des indicateurs...")).toHaveCount(0, { timeout: 10_000 });

  // 2 élèves actifs, 1 présent/1 absent (50%), 1 résultat saisi sur 2 attendus (50%), 1 bulletin
  // publié sur 2 générés — mêmes chiffres que apps/api/tests/test_dashboard.py.
  await expect(page.getByText("Élèves actifs")).toBeVisible();
  await expect(page.getByText("Taux de présence")).toBeVisible();
  await expect(page.getByText("Complétude des notes")).toBeVisible();
  await expect(page.getByText("Bulletins publiés")).toBeVisible();
  await expect(page.getByText("50%")).toHaveCount(2); // taux de présence + complétude des notes
  await expect(page.getByText("Terme-E2E").first()).toBeVisible(); // indication de période
  await expect(page.getByText("Aucune donnée")).toHaveCount(0); // toutes les métriques ont des données ici
});

test("tableau de bord : école vide affiche zéro et « Aucune donnée », jamais de blocage", async ({ page, request }) => {
  await registerSchool(page, request, "dashempty");
  await page.goto("/");

  await expect(page.getByText("Chargement des indicateurs...")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByText("Élèves actifs")).toBeVisible();
  await expect(page.getByText("Bulletins publiés")).toBeVisible();
  await expect(page.getByText("0", { exact: true })).toHaveCount(2); // élèves actifs + bulletins publiés
  await expect(page.getByText("Aucune donnée")).toHaveCount(2); // taux de présence + complétude des notes
});

test("tableau de bord : permission refusée affiche un message clair, pas un blocage infini", async ({ page, request }) => {
  const { schoolId, orgAdminToken } = await registerSchool(page, request, "dashperm");

  const accountantEmail = `dashperm-acct-${Date.now()}@wizard-e2e.example`;
  const created = await (
    await request.post(`${API_BASE_URL}/api/v1/users`, {
      headers: { Authorization: `Bearer ${orgAdminToken}` },
      data: { email: accountantEmail, full_name: "Comptable Test", school_id: schoolId, role_code: "ACCOUNTANT" },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: "AccountantPass123" },
  });

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(accountantEmail);
  await page.getByPlaceholder("Mot de passe").fill("AccountantPass123");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/");

  // getByRole("alert") remonterait aussi le route-announcer interne de Next.js
  // (#__next-route-announcer__, role="alert" lui aussi) — on cible donc le texte exact.
  await expect(page.getByText("Not enough permissions", { exact: true })).toBeVisible();
  await expect(page.getByText("Chargement des indicateurs...")).toHaveCount(0);
});
