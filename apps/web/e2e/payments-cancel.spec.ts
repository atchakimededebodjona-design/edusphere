import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { api, createUser, setupDesk, type Desk } from "./helpers/cashDesk";
import { TENANT_PASSWORD, clearResetPasswordRateLimit, loginInBrowser } from "./helpers/tenants";

// Lot 3 — page /payments : refus d'annulation (HTTP 409 session de caisse clôturée) et erreurs.
// Convention de la suite : vraie page, vrai client API, vrai backend. Le 409 « session clôturée »
// est un VRAI refus du backend (paiement rattaché à une caisse réellement clôturée via l'API).
// `page.route()` n'est utilisé que pour provoquer les variantes impossibles à obtenir proprement
// d'un backend sain (409 sans corps exploitable, 500, coupure réseau, réponse lente).

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

type Fixture = { desk: Desk; closedReceipt: string; freeReceipt: string };

async function pay(request: APIRequestContext, token: string, desk: Desk, amount: string): Promise<{ receipt_number: string }> {
  const [student] = await api(
    request,
    token,
    "GET",
    `/api/v1/cashier/students/search?school_id=${desk.tenant.schoolId}&search=${desk.matricule}`,
  );
  const summary = await api(request, token, "GET", `/api/v1/students/${student.id}/financial-summary`);
  return api(request, token, "POST", "/api/v1/payments", {
    student_id: student.id,
    amount,
    method: "CASH",
    paid_at: new Date().toISOString().slice(0, 10),
    idempotency_key: `cancel-e2e-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    allocations: [{ student_fee_id: summary.fees[0].id, amount }],
  });
}

/** Un paiement CASH du caissier dans une caisse ensuite CLÔTURÉE (vraie clôture API), et un
 * paiement de l'administrateur sans session (comportement historique, annulable). */
async function setup(request: APIRequestContext, prefix: string): Promise<Fixture> {
  const desk = await setupDesk(request, prefix);
  const closed = await pay(request, desk.cashierToken, desk, "5000");
  const current = await api(request, desk.cashierToken, "GET", `/api/v1/cash/sessions/current?school_id=${desk.tenant.schoolId}`);
  const sessionId = current.current.session.id;
  const count = await api(request, desk.cashierToken, "POST", `/api/v1/cash/sessions/${sessionId}/count`, {
    lines: [{ denomination: "5000", quantity: 1 }],
  });
  await api(request, desk.cashierToken, "POST", `/api/v1/cash/sessions/${sessionId}/close`, {
    count_id: count.id,
    expected_amount: current.current.totals.expected_amount, // fonds 0 + 5 000 : aucun écart
  });
  const free = await pay(request, desk.tenant.orgAdminToken, desk, "2000");
  return { desk, closedReceipt: closed.receipt_number, freeReceipt: free.receipt_number };
}

async function openPayments(page: Page, fixture: Fixture) {
  await loginInBrowser(page, fixture.desk.tenant.orgAdminEmail, fixture.desk.tenant.password);
  page.on("dialog", (dialog) => void dialog.accept("Erreur de saisie"));
  await page.goto("/payments");
  await expect(page.getByRole("heading", { name: "Paiements" })).toBeVisible();
}

const row = (page: Page, receipt: string) => page.locator("tr", { hasText: receipt });
const cancelButton = (page: Page, receipt: string) => row(page, receipt).getByRole("button", { name: /Annul/ });
const totalPaid = (page: Page) => page.locator("div", { has: page.getByText("Total encaissé", { exact: true }) }).last();
const cancelError = (page: Page) => page.getByTestId("payment-cancel-error");

test("annulation réussie : comportement existant, liste et totaux relus", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancelok");
  await openPayments(page, fixture);
  await expect(totalPaid(page)).toContainText("67000.00"); // 60 000 (amorce) + 5 000 + 2 000
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(row(page, fixture.freeReceipt)).toContainText("CANCELLED");
  await expect(cancelButton(page, fixture.freeReceipt)).toHaveCount(0);
  await expect(totalPaid(page)).toContainText("65000.00");
  await expect(cancelError(page)).toHaveCount(0);
});

test("409 réel (session clôturée) : message métier, paiement et totaux inchangés, aucun rafraîchissement", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancel409");
  await openPayments(page, fixture);
  const reloads: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "GET" && /\/api\/v1\/(payments\?|fees\/summary)/.test(request.url())) reloads.push(request.url());
  });
  const response = page.waitForResponse((r) => r.url().includes("/cancel") && r.request().method() === "POST");
  await cancelButton(page, fixture.closedReceipt).click();
  expect((await response).status()).toBe(409);

  await expect(cancelError(page)).toContainText(`Reçu ${fixture.closedReceipt}`);
  await expect(cancelError(page)).toContainText(
    "Annulation impossible : ce paiement appartient à une session de caisse déjà clôturée.",
  );
  await expect(row(page, fixture.closedReceipt)).toContainText("COMPLETED");
  await expect(cancelButton(page, fixture.closedReceipt)).toBeEnabled();
  await expect(cancelButton(page, fixture.closedReceipt)).toHaveText("Annuler");
  await expect(totalPaid(page)).toContainText("67000.00");
  expect(reloads).toEqual([]); // jamais de rechargement présentant l'annulation comme faite

  // Après rechargement complet, le paiement est toujours enregistré (le backend n'a rien changé).
  await page.reload();
  await expect(row(page, fixture.closedReceipt)).toContainText("COMPLETED");
  await expect(cancelError(page)).toHaveCount(0); // bandeau non persistant
});

test("409 sans message exploitable : message de repli", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancel409b");
  await openPayments(page, fixture);
  await page.route("**/api/v1/payments/*/cancel", (route) => route.fulfill({ status: 409, contentType: "text/plain", body: "" }));
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(cancelError(page)).toContainText("Annulation impossible : la session de caisse est clôturée.");
  await expect(row(page, fixture.freeReceipt)).toContainText("COMPLETED");
  await expect(cancelButton(page, fixture.freeReceipt)).toBeEnabled();
});

test("autre erreur HTTP (500) : message adapté, sans faux succès ni détail technique", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancel500");
  await openPayments(page, fixture);
  await page.route("**/api/v1/payments/*/cancel", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Traceback: db secret" }) }),
  );
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(cancelError(page)).toContainText("Erreur serveur : l'annulation n'a pas été effectuée. Réessayez plus tard.");
  await expect(cancelError(page)).not.toContainText("Traceback");
  await expect(row(page, fixture.freeReceipt)).toContainText("COMPLETED");
  await expect(totalPaid(page)).toContainText("67000.00");
  await expect(cancelButton(page, fixture.freeReceipt)).toBeEnabled();
});

test("erreur réseau : message adapté et bouton de nouveau utilisable", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancelnet");
  await openPayments(page, fixture);
  await page.route("**/api/v1/payments/*/cancel", (route) => route.abort("failed"));
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(cancelError(page)).toContainText(
    "La requête d'annulation n'a pas pu aboutir (problème de connexion). Vérifiez l'état du paiement avant de réessayer.",
  );
  await expect(cancelButton(page, fixture.freeReceipt)).toBeEnabled();
  await expect(row(page, fixture.freeReceipt)).toContainText("COMPLETED");

  // Le bandeau se ferme ; une nouvelle tentative (réseau rétabli) aboutit normalement.
  await page.getByRole("button", { name: "Fermer" }).click();
  await expect(cancelError(page)).toHaveCount(0);
  await page.unroute("**/api/v1/payments/*/cancel");
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(row(page, fixture.freeReceipt)).toContainText("CANCELLED");
});

test("double clic : une seule requête d'annulation, bouton désactivé pendant l'envoi puis réactivé", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcanceldbl");
  await openPayments(page, fixture);
  let posts = 0;
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/v1/payments/*/cancel", async (route) => {
    posts += 1;
    await held; // réponse retenue : on observe l'état "en cours"
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "x" }) });
  });

  // Deux clics dans la même tâche, avant tout nouveau rendu : seule la garde du composant protège.
  await row(page, fixture.freeReceipt)
    .getByRole("button", { name: "Annuler" })
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  const busy = row(page, fixture.freeReceipt).getByRole("button", { name: "Annulation..." });
  await expect(busy).toBeDisabled();
  await busy.click({ force: true }); // bouton désactivé : aucun nouvel envoi
  release();
  await expect(cancelError(page)).toContainText("Annulation impossible : x");
  await expect(cancelButton(page, fixture.freeReceipt)).toBeEnabled();
  expect(posts).toBe(1);
});

// --- Visibilité du bouton « Annuler » : `payments.cancel` (permission exigée par l'API) ------------
async function openPaymentsAs(page: Page, email: string) {
  await loginInBrowser(page, email, TENANT_PASSWORD);
  await page.goto("/payments");
}

test("permissions : payments.cancel voit Annuler ; payments.manage seul ne le voit pas, ses autres actions restent", async ({
  page,
}) => {
  const fixture = await setup(page.context().request, "pcancelperm");
  const request = page.context().request;

  // ACCOUNTANT (payments.cancel) : bouton visible sur un paiement COMPLETED.
  const accountantEmail = await createUser(request, fixture.desk.tenant, "ACCOUNTANT", "Agent Comptable");
  await openPaymentsAs(page, accountantEmail);
  await expect(row(page, fixture.freeReceipt).getByRole("button", { name: "Annuler" })).toBeVisible();
  await page.getByRole("button", { name: "Déconnexion" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // CAISSIER (payments.manage sans payments.cancel) : aucun bouton Annuler, mais la liste, le reçu
  // et le lien Caisse (payments.manage) restent disponibles.
  await openPaymentsAs(page, fixture.desk.cashierEmail);
  await expect(row(page, fixture.freeReceipt)).toContainText("COMPLETED");
  await expect(page.getByRole("button", { name: "Annuler" })).toHaveCount(0);
  await expect(row(page, fixture.freeReceipt).getByRole("button", { name: "Reçu" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Caisse", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Déconnexion" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // STAFF (ni payments.manage ni payments.cancel) : jamais de bouton Annuler.
  const staffEmail = await createUser(request, fixture.desk.tenant, "STAFF", "Agent Staff");
  await openPaymentsAs(page, staffEmail);
  await expect(page.getByRole("heading", { name: "Paiements" }).or(page.getByRole("button", { name: "Réessayer" }))).toBeVisible();
  await expect(page.getByRole("button", { name: "Annuler" })).toHaveCount(0);
});

test("403 : message de permission insuffisante, sans faux succès ni rafraîchissement", async ({ page }) => {
  const fixture = await setup(page.context().request, "pcancel403");
  await openPayments(page, fixture);
  const reloads: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "GET" && /\/api\/v1\/(payments\?|fees\/summary)/.test(request.url())) reloads.push(request.url());
  });
  await page.route("**/api/v1/payments/*/cancel", (route) =>
    route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Not enough permissions" }) }),
  );
  await cancelButton(page, fixture.freeReceipt).click();
  await expect(cancelError(page)).toContainText("Vous n'êtes pas autorisé à annuler ce paiement.");
  await expect(row(page, fixture.freeReceipt)).toContainText("COMPLETED");
  await expect(totalPaid(page)).toContainText("67000.00");
  await expect(cancelButton(page, fixture.freeReceipt)).toBeEnabled();
  expect(reloads).toEqual([]);
});
