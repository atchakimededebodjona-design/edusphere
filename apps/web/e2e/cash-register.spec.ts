import { expect, test, type Page } from "@playwright/test";
import { api, createUser, setupDesk, type Desk } from "./helpers/cashDesk";
import { TENANT_PASSWORD, clearResetPasswordRateLimit, createOrganizationViaPlatform, loginInBrowser } from "./helpers/tenants";

// Caisse scolaire, lot 3 — session de caisse : ouverture, encaissement, mouvement, comptage, écart,
// justification, clôture, historique, supervision. Parcours réel contre l'API + Postgres (même
// convention que cashier.spec.ts) ; aucun paiement en ligne.

test.beforeEach(() => {
  clearResetPasswordRateLimit();
});

async function collectCash(page: Page, desk: Desk, amount: string) {
  await page.goto("/cashier");
  await page.getByLabel("Rechercher un élève par nom, prénom ou matricule").fill(desk.matricule);
  await page.getByRole("button", { name: `Sélectionner ${desk.studentLastName} ${desk.studentFirstName}` }).click();
  await page.getByLabel(/Montant reçu/).fill(amount);
  await page.getByRole("button", { name: "Répartir automatiquement" }).click();
  await page.getByRole("button", { name: "Encaisser", exact: true }).click();
  await page.getByRole("button", { name: "Confirmer l'encaissement" }).click();
  await expect(page.getByRole("region", { name: "Encaissement enregistré" })).toBeVisible();
  return (await page.getByTestId("cash-receipt-number").textContent()) ?? "";
}

test("caissier : ouverture, encaissement, mouvement, comptage, écart justifié, clôture et historique", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashreg", { openSession: false });
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);

  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Ma caisse" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Supervision caisse" })).toHaveCount(0);

  // Sans caisse ouverte, le poste d'encaissement l'annonce (l'API refuse de toute façon).
  await page.goto("/cashier");
  await expect(page.getByTestId("cash-register-closed-banner")).toBeVisible();

  // Ouverture.
  await nav.getByRole("link", { name: "Ma caisse" }).click();
  await expect(page).toHaveURL("/cashier/cash-register");
  await expect(page.getByTestId("cash-session-status")).toHaveText("Aucune caisse ouverte");
  await page.getByLabel("Fonds de caisse initial").fill("10000");
  await page.getByRole("button", { name: "Ouvrir ma caisse" }).click();
  await expect(page.getByTestId("cash-session-status")).toHaveText("Caisse ouverte");
  await expect(page.getByTestId("cash-expected-amount")).toHaveText("10 000 FCFA");

  // Encaissement (poste lot 2), rattaché à la session.
  await page.goto("/cashier");
  await expect(page.getByTestId("cash-register-closed-banner")).toHaveCount(0);
  const receipt = await collectCash(page, desk, "15000");
  await page.goto("/cashier/cash-register");
  await expect(page.getByRole("list", { name: "Encaissements de la session" })).toContainText(receipt);
  await expect(page.getByTestId("cash-expected-amount")).toHaveText("25 000 FCFA");

  // Mouvement : versement en banque.
  await page.getByLabel("Type de mouvement").selectOption("BANK_DEPOSIT");
  await page.getByLabel("Montant du mouvement").fill("5000");
  await page.getByLabel("Motif du mouvement").fill("Versement agence centre");
  await page.getByLabel("Référence (facultatif)").fill("BORD-42");
  await page.getByRole("button", { name: "Enregistrer le mouvement" }).click();
  await expect(page.getByRole("list", { name: "Mouvements enregistrés" })).toContainText("Versement agence centre");
  await expect(page.getByTestId("cash-expected-amount")).toHaveText("20 000 FCFA");

  // Comptage par coupure : 19 000 (écart de -1 000).
  await page.getByLabel("Quantité de 10 000 FCFA").fill("1");
  await page.getByLabel("Quantité de 5 000 FCFA").fill("1");
  await page.getByLabel("Quantité de 2 000 FCFA").fill("2");
  await expect(page.getByTestId("cash-count-preview")).toHaveText("19 000 FCFA");
  await page.getByRole("button", { name: "Enregistrer le comptage" }).click();
  await expect(page.getByTestId("cash-counted-amount")).toHaveText("19 000 FCFA");
  await expect(page.getByTestId("cash-variance")).toHaveText("-1 000 FCFA");

  // Justification obligatoire avant clôture.
  const closeButton = page.getByRole("button", { name: "Clôturer la caisse" });
  await expect(closeButton).toBeDisabled();
  await page.getByLabel("Motif de l'écart").selectOption("CHANGE_ERROR");
  await expect(closeButton).toBeDisabled();
  await page.getByLabel("Justification de l'écart").fill("Monnaie rendue en trop à un parent");
  await expect(closeButton).toBeEnabled();
  await closeButton.click();

  await expect(page.getByTestId("cash-session-status")).toHaveText("Aucune caisse ouverte");
  await expect(page.getByTestId("cash-closed-banner")).toContainText("écart -1 000 FCFA");
  const history = page.getByRole("table", { name: "Historique de mes caisses" });
  await expect(history.getByTestId("cash-session-row")).toHaveCount(1);
  await expect(history).toContainText("Clôturée");
  await expect(history).toContainText("-1 000 FCFA");
  await expect(history).toContainText("Erreur de rendu de monnaie");

  // Après clôture : plus d'encaissement espèces sans nouvelle ouverture.
  await page.goto("/cashier");
  await expect(page.getByTestId("cash-register-closed-banner")).toBeVisible();
});

test("erreurs : sortie supérieure aux espèces disponibles, clôture sans comptage impossible", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashregerr", { openSession: false });
  await api(page.context().request, desk.cashierToken, "POST", "/api/v1/cash/sessions/open", {
    school_id: desk.tenant.schoolId,
    opening_amount: "1000",
  });
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await page.goto("/cashier/cash-register");
  await page.getByLabel("Type de mouvement").selectOption("CASH_OUT");
  await page.getByLabel("Montant du mouvement").fill("5000");
  await page.getByLabel("Motif du mouvement").fill("Achat fournitures");
  await page.getByRole("button", { name: "Enregistrer le mouvement" }).click();
  await expect(page.getByText("La sortie dépasse les espèces disponibles en caisse.")).toBeVisible();
  await expect(page.getByTestId("cash-expected-amount")).toHaveText("1 000 FCFA");
  await expect(page.getByText("Enregistrez un comptage physique pour calculer l'écart et clôturer.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clôturer la caisse" })).toHaveCount(0);
});

test("supervision : administrateur voit les caisses, le rapport du jour, le détail et exporte le CSV", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashsup");
  await api(page.context().request, desk.cashierToken, "POST", "/api/v1/payments", await (async () => {
    const students = await api(page.context().request, desk.cashierToken, "GET",
      `/api/v1/cashier/students/search?school_id=${desk.tenant.schoolId}&search=${desk.matricule}`);
    const summary = await api(page.context().request, desk.cashierToken, "GET", `/api/v1/students/${students[0].id}/financial-summary`);
    return {
      student_id: students[0].id,
      amount: "7000",
      method: "CASH",
      paid_at: new Date().toISOString().slice(0, 10),
      idempotency_key: `sup-${Date.now()}`,
      allocations: [{ student_fee_id: summary.fees[0].id, amount: "7000" }],
    };
  })());

  await loginInBrowser(page, desk.tenant.orgAdminEmail, desk.tenant.password);
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Supervision caisse" })).toBeVisible();
  await nav.getByRole("link", { name: "Supervision caisse" }).click();
  await expect(page).toHaveURL("/cashier/supervision");
  await expect(page.getByRole("heading", { name: "Supervision des caisses" })).toBeVisible();
  await expect(page.getByTestId("cash-daily-report")).toContainText("1 (1 / 0)");
  await expect(page.getByTestId("cash-daily-report")).toContainText("7 000 FCFA");

  const sessions = page.getByRole("table", { name: "Sessions de caisse" });
  await expect(sessions).toContainText("Kodjo Caissier");
  await expect(sessions).toContainText("Ouverte");
  await sessions.getByRole("button", { name: "Détail" }).click();
  const detail = page.getByRole("region", { name: "Détail de la session" });
  await expect(detail).toContainText("Session de Kodjo Caissier");
  await expect(detail.getByTestId("cash-expected-amount")).toHaveText("7 000 FCFA");
  await expect(page.getByRole("list", { name: "Rapport par caissier" })).toContainText("Kodjo Caissier");
  await expect(page.getByRole("list", { name: "Rapport par méthode" })).toContainText("Espèces");

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Exporter CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^caisse_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.csv$/);
});

test("permissions : caissier sans supervision, personnel sans caisse", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashperm");
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await page.goto("/cashier/supervision");
  await expect(page.getByText("Cet espace est réservé aux superviseurs de caisse.")).toBeVisible();
  await page.getByRole("button", { name: "Déconnexion" }).click();
  await expect(page).toHaveURL(/\/login$/);

  const tenant = await createOrganizationViaPlatform(page.context().request, "cashpermstaff");
  const staffEmail = await createUser(page.context().request, tenant, "STAFF", "Agent Staff");
  await loginInBrowser(page, staffEmail, TENANT_PASSWORD);
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Ma caisse" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Supervision caisse" })).toHaveCount(0);
  await page.goto("/cashier/cash-register");
  await expect(page.getByText("Cet espace est réservé aux comptes disposant d'une caisse.")).toBeVisible();
});

test("mobile : ma caisse utilisable sans défilement horizontal", async ({ page }) => {
  const desk = await setupDesk(page.context().request, "cashregmob");
  await page.setViewportSize({ width: 390, height: 844 });
  await loginInBrowser(page, desk.cashierEmail, TENANT_PASSWORD);
  await page.goto("/cashier/cash-register");
  await expect(page.getByTestId("cash-session-status")).toHaveText("Caisse ouverte");
  await page.getByLabel("Quantité de 1 FCFA").fill("0");
  await page.getByRole("button", { name: "Enregistrer le comptage" }).click();
  await expect(page.getByTestId("cash-variance")).toHaveText("0 FCFA");
  await expect(page.getByRole("button", { name: "Clôturer la caisse" })).toBeEnabled();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
