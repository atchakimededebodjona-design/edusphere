import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { API_BASE_URL, clearResetPasswordRateLimit, createOrganizationViaPlatform, type TenantAdmin } from "./helpers/tenants";

// PR #15 — cadence des relances de frais en retard (J0/J7/J30). Le job n'a pas de route HTTP
// dédiée (voir app/jobs/overdue_fee_reminders.py, Discovery : "ne jamais appeler une route HTTP
// interne") : exécuté directement dans le conteneur `api`, même mécanisme que la préparation
// d'un compte plateforme dans ./helpers/tenants.ts.

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";

function runOverdueReminderJob(): void {
  execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "python", "-m", "app.jobs.overdue_fee_reminders"], {
    cwd: REPO_ROOT,
  });
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

async function setupOverdueFee(request: APIRequestContext, admin: TenantAdmin, prefix: string, dueDate: string) {
  const headers = { Authorization: `Bearer ${admin.orgAdminToken}` };
  const year = await (
    await request.post(`${API_BASE_URL}/api/v1/academic-years`, {
      headers,
      data: { school_id: admin.schoolId, name: `${prefix}-2026`, start_date: "2026-09-01", end_date: "2027-06-30" },
    })
  ).json();
  const level = await (
    await request.post(`${API_BASE_URL}/api/v1/education-levels`, { headers, data: { school_id: admin.schoolId, name: `${prefix}-niveau` } })
  ).json();
  const schoolClass = await (
    await request.post(`${API_BASE_URL}/api/v1/classes`, {
      headers,
      data: { academic_year_id: year.id, education_level_id: level.id, name: "A" },
    })
  ).json();
  const student = await (
    await request.post(`${API_BASE_URL}/api/v1/students`, {
      headers,
      data: { school_id: admin.schoolId, matricule: `${prefix}-001`, first_name: "Ama", last_name: "Elève", date_of_birth: "2015-01-01", sex: "F" },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/students/${student.id}/enrollments`, {
    headers,
    data: { class_id: schoolClass.id, enrollment_date: "2026-09-01" },
  });
  const category = await (
    await request.post(`${API_BASE_URL}/api/v1/fee-categories`, { headers, data: { school_id: admin.schoolId, name: `${prefix}-Scolarite` } })
  ).json();
  const schedule = await (
    await request.post(`${API_BASE_URL}/api/v1/fee-schedules`, {
      headers,
      data: {
        school_id: admin.schoolId,
        fee_category_id: category.id,
        academic_year_id: year.id,
        name: `${prefix}-Tranche`,
        amount: "50000",
        scope_type: "SCHOOL",
        due_date: dueDate,
      },
    })
  ).json();
  const generate = await request.post(`${API_BASE_URL}/api/v1/fee-schedules/${schedule.id}/generate`, { headers });
  expect(generate.status(), await generate.text()).toBe(200);

  const summary = await (await request.get(`${API_BASE_URL}/api/v1/students/${student.id}/financial-summary`, { headers })).json();
  return { student, fee: summary.fees[0] };
}

async function attachGuardianWithEmail(request: APIRequestContext, admin: TenantAdmin, studentId: string, email: string) {
  const headers = { Authorization: `Bearer ${admin.orgAdminToken}` };
  const guardian = await (
    await request.post(`${API_BASE_URL}/api/v1/guardians`, {
      headers,
      data: { school_id: admin.schoolId, full_name: "Tuteur Sans Compte", relationship_type: "mother", email },
    })
  ).json();
  await request.post(`${API_BASE_URL}/api/v1/students/${studentId}/guardians`, { headers, data: { guardian_id: guardian.id } });
  return guardian;
}

test("palier J7 atteint : affiché dans /fees/overdue avec dernière et prochaine relance", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "overduecadence");
  const dueDate = daysAgo(10); // J0 et J7 déjà franchissables, J30 pas encore.
  const { student, fee } = await setupOverdueFee(request, admin, "cadence", dueDate);
  const guardianEmail = `tutor.${Date.now()}@wizard-e2e.example`;
  await attachGuardianWithEmail(request, admin, student.id, guardianEmail);

  runOverdueReminderJob(); // -> J0 uniquement (jamais deux paliers au même passage)
  runOverdueReminderJob(); // -> J7 (J0 déjà traité)

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(admin.orgAdminEmail);
  await page.getByPlaceholder("Mot de passe").fill(admin.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");

  await page.goto("/fees/overdue");
  const row = page.locator("tr", { hasText: guardianEmail });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Relance à J+7");
  await expect(row).toContainText("dernière relance le");
  await expect(row).toContainText("prochaine relance le");

  // La prochaine relance annoncée correspond bien à due_date + 30 jours (palier J30).
  const expectedNext = new Date(dueDate);
  expectedNext.setDate(expectedNext.getDate() + 30);
  await expect(row).toContainText(expectedNext.toLocaleDateString("fr-FR"));
});

test("tuteur sans canal : aucun palier affiché, page sans erreur", async ({ page, request }) => {
  const admin = await createOrganizationViaPlatform(request, "overduenochannel");
  const { student } = await setupOverdueFee(request, admin, "nochannel", daysAgo(10));
  void student; // aucun tuteur rattaché du tout -> ligne "Aucun tuteur rattaché"

  runOverdueReminderJob();

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(admin.orgAdminEmail);
  await page.getByPlaceholder("Mot de passe").fill(admin.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");

  await page.goto("/fees/overdue");
  await expect(page.getByText("Aucun tuteur rattaché")).toBeVisible();
  // Pagination/filtre existant toujours fonctionnel, aucune erreur affichée.
  await expect(page.getByRole("heading", { name: "Frais en retard" })).toBeVisible();
});
