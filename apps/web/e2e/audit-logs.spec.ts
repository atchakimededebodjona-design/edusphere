import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  API_BASE_URL,
  clearResetPasswordRateLimit,
  registerOrgAdminInBrowser,
  TENANT_PASSWORD,
  type TenantAdmin,
} from "./helpers/tenants";

// PR #14 — journal d'audit administratif. Une action sensible réelle (ici : désactivation d'un
// compte utilisateur, déclenchée depuis l'UI /users) doit apparaître dans /audit-logs, filtrable,
// et rester invisible à un rôle non autorisé (TEACHER).

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

async function createTeacher(request: APIRequestContext, admin: TenantAdmin, prefix: string) {
  const email = `${prefix}-${Date.now()}@wizard-e2e.example`;
  const response = await request.post(`${API_BASE_URL}/api/v1/users`, {
    headers: { Authorization: `Bearer ${admin.orgAdminToken}` },
    data: { email, full_name: "Enseignant Test", school_id: admin.schoolId, role_code: "TEACHER" },
  });
  expect(response.status(), await response.text()).toBe(201);
  const body = await response.json();
  return { id: body.user.id as string, email, full_name: body.user.full_name as string };
}

test("désactivation d'un utilisateur : l'événement apparaît dans le journal d'audit, filtrable", async ({ page, request }) => {
  const admin = await registerOrgAdminInBrowser(page, "auditlogmain");
  const teacher = await createTeacher(request, admin, "auditlogmain-teacher");

  await page.goto("/users");
  const row = page.locator("tr", { hasText: teacher.email });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Désactiver" }).click();
  await row.getByRole("button", { name: "Oui" }).click();
  await expect(row.getByText("Inactif")).toBeVisible();

  await page.goto("/audit-logs");
  const auditRow = page.locator('[data-testid="audit-log-row"]', { hasText: teacher.email });
  await expect(auditRow).toBeVisible();
  await expect(auditRow).toContainText("Statut utilisateur changé");

  // Filtre par type d'entité : la ligne reste visible (c'est bien un événement "Utilisateur").
  await page.getByLabel("Type d'entité").selectOption({ label: "Utilisateur" });
  await expect(page.locator('[data-testid="audit-log-row"]', { hasText: teacher.email })).toBeVisible();

  // Filtre par action incompatible : la ligne disparaît, remplacée par l'état vide.
  await page.getByLabel("Type d'entité").selectOption({ label: "Tous" });
  await page.getByLabel("Action").selectOption({ label: "Paiement annulé" });
  await expect(page.getByText("Aucun événement d'audit.")).toBeVisible();
});

test("un enseignant n'atteint jamais le journal d'audit (redirigé vers /teacher)", async ({ page }) => {
  const admin = await registerOrgAdminInBrowser(page, "auditlogrbac");

  // Le compte créé via POST /users n'a pas encore de mot de passe défini — on en fixe un via le
  // lien de réinitialisation dev, même mécanisme que les autres specs E2E de ce dépôt.
  const createResponse = await page.context().request.post(`${API_BASE_URL}/api/v1/users`, {
    headers: { Authorization: `Bearer ${admin.orgAdminToken}` },
    data: {
      email: `rbac-${Date.now()}@wizard-e2e.example`,
      full_name: "Enseignant RBAC",
      school_id: admin.schoolId,
      role_code: "TEACHER",
    },
  });
  const created = await createResponse.json();
  await page.context().request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: TENANT_PASSWORD },
  });

  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(created.user.email);
  await page.getByPlaceholder("Mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/teacher");

  await page.goto("/audit-logs");
  await expect(page).toHaveURL("/teacher");
});
