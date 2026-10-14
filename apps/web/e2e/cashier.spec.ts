import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import {
  API_BASE_URL,
  TENANT_PASSWORD,
  clearResetPasswordRateLimit,
  createOrganizationViaPlatform,
  loginInBrowser,
  unique,
  type TenantAdmin,
} from "./helpers/tenants";

// Caisse scolaire, lot 2 — poste d'encaissement /cashier. Même convention que le reste de la suite
// (voir auth-session-resilience.spec.ts) : parcours réel contre l'API + Postgres, sans mock, SAUF
// le scénario d'erreur API où `page.route()` provoque de façon ciblée une réponse en échec.
// Aucun paiement en ligne : seul `POST /payments` (method CASH) est exercé.

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

type Desk = { tenant: TenantAdmin; studentLastName: string; studentFirstName: string; matricule: string; cashierEmail: string };

async function api(request: APIRequestContext, token: string, method: "GET" | "POST", path: string, data?: unknown) {
  const response = await request.fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

async function createUser(request: APIRequestContext, tenant: TenantAdmin, roleCode: string, fullName: string): Promise<string> {
  const email = `${unique(roleCode.toLowerCase()).toLowerCase()}@wizard-e2e.example`;
  const created = await api(request, tenant.orgAdminToken, "POST", "/api/v1/users", {
    email,
    full_name: fullName,
    school_id: tenant.schoolId,
    role_code: roleCode,
  });
  const reset = await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: TENANT_PASSWORD },
  });
  expect(reset.status()).toBe(204);
  return email;
}

/** Élève avec deux frais — Scolarité 150 000 (échéance proche, 50 000 déjà payés) et Cantine 30 000
 * (échéance plus lointaine, 10 000 déjà payés) : total restant 120 000 FCFA, comme l'exemple métier. */
async function setupDesk(request: APIRequestContext, prefix: string): Promise<Desk> {
  const tenant = await createOrganizationViaPlatform(request, prefix);
  const token = tenant.orgAdminToken;
  const schoolId = tenant.schoolId;
  const year = await api(request, token, "POST", "/api/v1/academic-years", {
    school_id: schoolId,
    name: `${prefix}-2026`,
    start_date: "2026-09-01",
    end_date: "2027-06-30",
  });
  const level = await api(request, token, "POST", "/api/v1/education-levels", { school_id: schoolId, name: "CM1" });
  const schoolClass = await api(request, token, "POST", "/api/v1/classes", {
    academic_year_id: year.id,
    education_level_id: level.id,
    name: "CM1 A",
  });
  const matricule = unique("CAISSE").toUpperCase();
  const studentLastName = `Mensah${unique("").slice(-5)}`;
  const studentFirstName = "Ama";
  const student = await api(request, token, "POST", "/api/v1/students", {
    school_id: schoolId,
    matricule,
    first_name: studentFirstName,
    last_name: studentLastName,
    date_of_birth: "2015-01-01",
    sex: "F",
  });
  await api(request, token, "POST", `/api/v1/students/${student.id}/enrollments`, {
    class_id: schoolClass.id,
    enrollment_date: "2026-09-01",
  });

  const feeIds: Record<string, string> = {};
  for (const [name, amount, dueDate] of [
    ["Scolarité", "150000", "2026-10-15"],
    ["Cantine", "30000", "2026-12-15"],
  ] as const) {
    const category = await api(request, token, "POST", "/api/v1/fee-categories", { school_id: schoolId, name });
    const schedule = await api(request, token, "POST", "/api/v1/fee-schedules", {
      school_id: schoolId,
      fee_category_id: category.id,
      academic_year_id: year.id,
      name,
      amount,
      scope_type: "SCHOOL",
      due_date: dueDate,
    });
    await api(request, token, "POST", `/api/v1/fee-schedules/${schedule.id}/generate`);
  }
  const summary = await api(request, token, "GET", `/api/v1/students/${student.id}/financial-summary`);
  for (const fee of summary.fees) feeIds[fee.fee_schedule_name] = fee.id;
  await api(request, token, "POST", "/api/v1/payments", {
    student_id: student.id,
    amount: "60000",
    method: "CASH",
    paid_at: "2026-10-01",
    idempotency_key: unique("seedpay"),
    allocations: [
      { student_fee_id: feeIds["Scolarité"], amount: "50000" },
      { student_fee_id: feeIds["Cantine"], amount: "10000" },
    ],
  });

  const cashierEmail = await createUser(request, tenant, "CAISSIER", "Kodjo Caissier");
  return { tenant, studentLastName, studentFirstName, matricule, cashierEmail };
}

async function openDeskAndSelectStudent(page: Page, desk: Desk, term: string) {
  await page.goto("/cashier");
  await expect(page.getByRole("heading", { name: "Caisse scolaire" })).toBeVisible();
  await page.getByLabel("Rechercher un élève par nom, prénom ou matricule").fill(term);
  await page.getByRole("button", { name: `Sélectionner ${desk.studentLastName} ${desk.studentFirstName}` }).click();
  await expect(page.getByTestId("cash-selected-student")).toHaveText(`${desk.studentLastName} ${desk.studentFirstName}`);
}

const encaisser = (page: Page) => page.getByRole("button", { name: "Encaisser", exact: true });
const allocationInput = (page: Page, feeName: string) => page.getByLabel(`Montant affecté — ${feeName}`);

test("caissier : recherche, situation, répartition, confirmation, reçu et historique", async ({ page, context }) => {
  const desk = await setupDesk(page.context().request, "cashdesk");
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);

  // Navigation : Caisse ET Paiements visibles pour le CAISSIER.
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Caisse" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Paiements" })).toBeVisible();
  await nav.getByRole("link", { name: "Caisse" }).click();
  await expect(page).toHaveURL("/cashier");
  await expect(page.getByText("Aucun encaissement enregistré aujourd'hui.")).toBeVisible();

  // Recherche : 1 caractère -> aucune requête, consigne affichée ; recherche partielle par nom.
  const search = page.getByLabel("Rechercher un élève par nom, prénom ou matricule");
  await search.fill("M");
  await expect(page.getByText("Saisissez au moins 2 caractères.")).toBeVisible();
  await search.fill(desk.studentLastName.slice(0, 8));
  const results = page.getByRole("list", { name: "Résultats de recherche" });
  await expect(results.getByText(`${desk.matricule} · CM1 A`)).toBeVisible();
  await results.getByRole("button", { name: `Sélectionner ${desk.studentLastName} ${desk.studentFirstName}` }).click();

  // Élève sélectionné + situation des frais.
  await expect(page.getByTestId("cash-selected-student")).toHaveText(`${desk.studentLastName} ${desk.studentFirstName}`);
  await expect(page.getByText(`Matricule : ${desk.matricule} · Classe : CM1 A`)).toBeVisible();
  const fees = page.getByTestId("fee-situation-item");
  await expect(fees).toHaveCount(2);
  const scolarite = fees.filter({ hasText: "Scolarité" });
  await expect(scolarite).toContainText("150 000 FCFA");
  await expect(scolarite).toContainText("50 000 FCFA");
  await expect(scolarite).toContainText("100 000 FCFA");
  await expect(scolarite).toContainText("Partiellement payé");
  await expect(scolarite).toContainText("Échéance : 15/10/2026");
  const cantine = fees.filter({ hasText: "Cantine" });
  await expect(cantine).toContainText("30 000 FCFA");
  await expect(cantine).toContainText("20 000 FCFA");
  await expect(page.getByTestId("fee-total-remaining")).toHaveText("120 000 FCFA");

  // Mode de paiement : ESPÈCES en lecture seule, aucun autre moyen proposé.
  const mode = page.getByLabel("Mode de paiement");
  await expect(mode).toHaveValue("ESPÈCES");
  await expect(mode).toHaveAttribute("readonly", "");
  for (const other of ["Virement", "Chèque", "Dépôt agent", "BANK_TRANSFER"]) {
    await expect(page.getByText(other, { exact: true })).toHaveCount(0);
  }

  // Bouton bloqué tant que montant <= 0 / somme != montant / dépassement de solde.
  await expect(encaisser(page)).toBeDisabled();
  await page.getByLabel(/Montant reçu/).fill("50000");
  await expect(page.getByTestId("cash-amount-received")).toHaveText("50 000 FCFA");
  await expect(encaisser(page)).toBeDisabled();
  await allocationInput(page, "Scolarité").fill("40000");
  await allocationInput(page, "Cantine").fill("5000");
  await expect(page.getByTestId("cash-total-allocated")).toHaveText("45 000 FCFA");
  await expect(page.getByTestId("cash-unallocated")).toHaveText("5 000 FCFA");
  await expect(encaisser(page)).toBeDisabled();
  await allocationInput(page, "Cantine").fill("25000");
  await expect(page.getByText("Dépasse le solde", { exact: true })).toBeVisible();
  await expect(encaisser(page)).toBeDisabled();
  await allocationInput(page, "Cantine").fill("10000");
  await expect(page.getByTestId("cash-unallocated")).toHaveText("0 FCFA");
  await expect(encaisser(page)).toBeEnabled();
  await page.getByLabel(/Montant reçu/).fill("0");
  await expect(encaisser(page)).toBeDisabled();

  // Répartir automatiquement : échéance la plus proche d'abord, jamais au-delà d'un solde.
  await page.getByLabel(/Montant reçu/).fill("110000");
  await page.getByRole("button", { name: "Répartir automatiquement" }).click();
  await expect(allocationInput(page, "Scolarité")).toHaveValue("100000");
  await expect(allocationInput(page, "Cantine")).toHaveValue("10000");
  // Tout payer : montant = total des soldes, chaque frais soldé.
  await page.getByRole("button", { name: /Tout payer/ }).click();
  await expect(page.getByLabel(/Montant reçu/)).toHaveValue("120000");
  await expect(allocationInput(page, "Cantine")).toHaveValue("20000");

  // Encaissement réel de 50 000 : 40 000 Scolarité + 10 000 Cantine.
  await page.getByLabel(/Montant reçu/).fill("50000");
  await allocationInput(page, "Scolarité").fill("40000");
  await allocationInput(page, "Cantine").fill("10000");
  await encaisser(page).click();

  const recap = page.getByRole("region", { name: "Récapitulatif de l'encaissement" });
  await expect(recap).toContainText(`${desk.studentLastName} ${desk.studentFirstName}`);
  await expect(recap).toContainText("50 000 FCFA");
  await expect(recap).toContainText("ESPÈCES");
  await expect(recap.getByRole("listitem").filter({ hasText: "Scolarité" })).toContainText("40 000 FCFA");
  await expect(recap.getByRole("listitem").filter({ hasText: "Cantine" })).toContainText("10 000 FCFA");

  const paymentRequests: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v1/payments")) paymentRequests.push(request.postData() ?? "");
  });
  await page.getByRole("button", { name: "Confirmer l'encaissement" }).click();

  const success = page.getByRole("region", { name: "Encaissement enregistré" });
  await expect(success).toBeVisible();
  const receiptNumber = (await page.getByTestId("cash-receipt-number").textContent()) ?? "";
  expect(receiptNumber).toMatch(/^RCPT-[0-9A-F]{10}$/);
  await expect(success).toContainText("50 000 FCFA");
  await expect(success).toContainText("Kodjo Caissier");
  await expect(page.getByTestId("cash-new-balance")).toHaveText("70 000 FCFA");
  expect(paymentRequests).toHaveLength(1);
  const sent = JSON.parse(paymentRequests[0]);
  expect(sent.method).toBe("CASH");
  expect(sent.amount).toBe("50000.00");
  expect(sent.idempotency_key).toMatch(/^cash-/);

  // Historique "Mes encaissements" mis à jour.
  const history = page.getByRole("list", { name: "Encaissements du jour" });
  await expect(history.getByText(receiptNumber)).toBeVisible();
  await expect(history).toContainText("Espèces");
  await expect(page.getByTestId("cash-day-total")).toHaveText("50 000 FCFA");

  // Reçu PDF existant, ouvert dans un nouvel onglet.
  // (Chromium headless traite un PDF comme un téléchargement : on vérifie l'onglet ouvert et la
  // réponse réelle de l'endpoint de reçu existant, pas le rendu du visualiseur PDF.)
  const receiptResponse = page.waitForResponse((response) => response.url().endsWith("/receipt.pdf"));
  const [receiptTab] = await Promise.all([context.waitForEvent("page"), success.getByRole("button", { name: "Voir le reçu" }).click()]);
  const receipt = await receiptResponse;
  expect(receipt.status()).toBe(200);
  expect(receipt.headers()["content-type"]).toContain("application/pdf");
  await receiptTab.close();

  await page.getByRole("button", { name: "Nouvel encaissement" }).click();
  await expect(page.getByLabel("Rechercher un élève par nom, prénom ou matricule")).toBeVisible();
});

test("erreur API à la confirmation : message affiché, puis nouvelle tentative avec la même clé", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "casherr");
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await openDeskAndSelectStudent(page, desk, desk.matricule);

  await page.getByLabel(/Montant reçu/).fill("20000");
  await page.getByRole("button", { name: "Répartir automatiquement" }).click();
  await encaisser(page).click();

  const sentKeys: string[] = [];
  let failNext = true;
  await page.route("**/api/v1/payments", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    sentKeys.push(JSON.parse(route.request().postData() ?? "{}").idempotency_key);
    if (failNext) {
      failNext = false;
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Service indisponible" }) });
    }
    return route.continue();
  });

  await page.getByRole("button", { name: "Confirmer l'encaissement" }).click();
  await expect(page.getByText("L'encaissement a échoué : Service indisponible")).toBeVisible();
  await expect(page.getByRole("region", { name: "Encaissement enregistré" })).toHaveCount(0);

  await page.getByRole("button", { name: "Confirmer l'encaissement" }).click();
  await expect(page.getByRole("region", { name: "Encaissement enregistré" })).toBeVisible();
  expect(sentKeys).toHaveLength(2);
  expect(sentKeys[0]).toBe(sentKeys[1]); // même opération = même clé d'idempotence
});

test("backend reste l'autorité : un refus serveur est affiché tel quel, rien n'est enregistré", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashdeny");
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await openDeskAndSelectStudent(page, desk, desk.studentLastName);
  await page.getByLabel(/Montant reçu/).fill("1000");
  await page.getByRole("button", { name: "Répartir automatiquement" }).click();
  await encaisser(page).click();
  await page.route("**/api/v1/payments", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Cashiers can only record cash payments" }),
        })
      : route.continue(),
  );
  await page.getByRole("button", { name: "Confirmer l'encaissement" }).click();
  await expect(page.getByText("Un caissier ne peut enregistrer que des paiements en espèces.")).toBeVisible();
  await expect(page.getByText("Aucun encaissement enregistré aujourd'hui.")).toBeVisible();
});

test("sans payments.manage : pas de lien Caisse et page réservée", async ({ page }) => {
  const tenant = await createOrganizationViaPlatform(page.context().request, "cashstaff");
  const staffEmail = await createUser(page.context().request, tenant, "STAFF", "Agent Staff");
  await loginInBrowser(page, staffEmail, TENANT_PASSWORD);
  await expect(page.getByRole("navigation").getByRole("link", { name: "Caisse" })).toHaveCount(0);
  await page.goto("/cashier");
  await expect(page.getByText("Cet espace est réservé aux comptes autorisés à enregistrer des paiements.")).toBeVisible();
  await expect(page.getByLabel("Rechercher un élève par nom, prénom ou matricule")).toHaveCount(0);
});

test("non connecté : /cashier renvoie vers la connexion", async ({ page }) => {
  await page.goto("/cashier");
  await expect(page).toHaveURL(/\/login$/);
});

test("administrateur d'école : lien Caisse visible, Paiements conservé", async ({ page }) => {
  const tenant = await createOrganizationViaPlatform(page.context().request, "cashadmin");
  await loginInBrowser(page, tenant.orgAdminEmail, tenant.password);
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Caisse" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Paiements" })).toBeVisible();
});

test("mobile : poste de caisse utilisable sans défilement horizontal", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashmobile");
  await page.setViewportSize({ width: 390, height: 844 });
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await openDeskAndSelectStudent(page, desk, desk.matricule);
  await expect(page.getByTestId("fee-total-remaining")).toHaveText("120 000 FCFA");
  await page.getByLabel(/Montant reçu/).fill("20000");
  await page.getByRole("button", { name: "Répartir automatiquement" }).click();
  await expect(encaisser(page)).toBeEnabled();
  await expect(encaisser(page)).toBeInViewport();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
