import { expect, test, type Page } from "@playwright/test";
import { registerOrgAdminInBrowser } from "./helpers/tenants";

// Phase 9 — infrastructure d'email transactionnel : exécuté contre l'API + Postgres réels
// (docker compose), sans mock. `dev_token`/`dev_reset_token` restent, comme dans les specs
// précédentes (setup-wizard, admin-onboarding), un mécanisme de PRÉPARATION de test — obtenir un
// jeton valide sans lire une vraie boîte mail — pas une simulation du parcours lui-même : les
// pages /forgot-password et /reset-password ci-dessous sont pilotées entièrement via l'UI réelle.

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";

function unique(prefix: string): string {
  return `${prefix}${Date.now()}${Math.floor(Math.random() * 10000)}`;
}

async function registerSchool(page: Page, slugPrefix: string) {
  const tenant = await registerOrgAdminInBrowser(page, slugPrefix);
  return { email: tenant.orgAdminEmail, password: tenant.password };
}

// Le texte indicatif suit la règle du mot de passe (lib/auth/passwordRule.ts : 12 caractères minimum
// depuis la revue de sécurité) ; seul son début est vérifié, pour ne pas dépendre du chiffre.
const NEW_PASSWORD_PLACEHOLDER = /^Nouveau mot de passe/;

test("mot de passe oublié : message générique, jamais de fuite d'existence de compte", async ({ page }) => {
  const { email } = await registerSchool(page, "pwforgot");
  await page.goto("/login");
  await page.getByRole("link", { name: "Mot de passe oublié ?" }).click();
  await expect(page).toHaveURL("/forgot-password");

  // Compte existant : même message que pour un compte inexistant (vérifié juste après).
  await page.getByPlaceholder("Email").fill(email);
  await page.getByRole("button", { name: "Envoyer le lien" }).click();
  const confirmationText = "Si un compte existe pour cette adresse, un email contenant un lien de réinitialisation";
  await expect(page.getByText(confirmationText)).toBeVisible();

  await page.goto("/forgot-password");
  await page.getByPlaceholder("Email").fill("personne-de-connu@wizard-e2e.example");
  await page.getByRole("button", { name: "Envoyer le lien" }).click();
  await expect(page.getByText(confirmationText)).toBeVisible();
});

test("lien de réinitialisation invalide : message clair, pas de plantage", async ({ page }) => {
  await page.goto("/reset-password?token=un-jeton-qui-n-existe-pas");
  await page.getByPlaceholder(NEW_PASSWORD_PLACEHOLDER).fill("NouveauPass123");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("NouveauPass123");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  // Refus du jeton traduit en français (phase 4 C de la refonte).
  await expect(page.getByText(/Ce lien n'est plus valable/)).toBeVisible();
});

test("réinitialisation réelle via l'UI : lien reçu -> nouveau mot de passe -> connexion", async ({ page, request }) => {
  const { email } = await registerSchool(page, "pwreset");

  // Préparation : obtenir un jeton valide sans lire une vraie boîte mail (voir commentaire en
  // tête de fichier) — l'API a réellement déclenché un envoi (vérifié côté backend par
  // apps/api/tests/test_email.py), on récupère ici seulement le jeton pour piloter l'UI.
  const forgotResponse = await request.post(`${API_BASE_URL}/api/v1/auth/forgot-password`, {
    data: { email },
  });
  const { dev_token: token } = await forgotResponse.json();
  expect(token).toBeTruthy();

  await page.goto(`/reset-password?token=${token}`);
  await page.getByPlaceholder(NEW_PASSWORD_PLACEHOLDER).fill("BrandNewPassword1");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("BrandNewPassword1");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  await expect(page.getByText("Votre mot de passe a été défini.")).toBeVisible();
  await page.getByRole("button", { name: "Aller à la connexion" }).click();
  await expect(page).toHaveURL("/login");

  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill("BrandNewPassword1");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

test("les deux mots de passe doivent correspondre", async ({ page, request }) => {
  const { email } = await registerSchool(page, "pwmismatch");
  const forgotResponse = await request.post(`${API_BASE_URL}/api/v1/auth/forgot-password`, {
    data: { email },
  });
  const { dev_token: token } = await forgotResponse.json();

  await page.goto(`/reset-password?token=${token}`);
  await page.getByPlaceholder(NEW_PASSWORD_PLACEHOLDER).fill("PasswordA123");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("PasswordB456");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  await expect(page.getByText("Les deux mots de passe ne correspondent pas.")).toBeVisible();
});
