import { expect, test, type Page } from "@playwright/test";

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
  const slug = unique(slugPrefix).toLowerCase();
  const email = `${slug}@wizard-e2e.example`;
  const password = "SuperSecret123";

  await page.goto("/register");
  await page.getByPlaceholder("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'organisation").fill(slug);
  await page.getByPlaceholder("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByPlaceholder("Identifiant (slug) de l'école").fill(slug);
  await page.getByPlaceholder("Votre nom complet").fill("Admin Test");
  await page.getByPlaceholder("Votre email").fill(email);
  await page.getByPlaceholder("Mot de passe (8 caractères min.)").fill(password);
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL("/");

  return { email, password };
}

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
  await page.getByPlaceholder("Nouveau mot de passe (8 caractères min.)").fill("NouveauPass123");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("NouveauPass123");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  await expect(page.getByText("Invalid or expired reset token")).toBeVisible();
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
  await page.getByPlaceholder("Nouveau mot de passe (8 caractères min.)").fill("BrandNewPassword1");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("BrandNewPassword1");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  await expect(page.getByText("Votre mot de passe a été défini.")).toBeVisible();
  await page.getByRole("button", { name: "Aller à la connexion" }).click();
  await expect(page).toHaveURL("/login");

  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill("BrandNewPassword1");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText(/Bienvenue sur l'espace de/)).toBeVisible();
});

test("les deux mots de passe doivent correspondre", async ({ page, request }) => {
  const { email } = await registerSchool(page, "pwmismatch");
  const forgotResponse = await request.post(`${API_BASE_URL}/api/v1/auth/forgot-password`, {
    data: { email },
  });
  const { dev_token: token } = await forgotResponse.json();

  await page.goto(`/reset-password?token=${token}`);
  await page.getByPlaceholder("Nouveau mot de passe (8 caractères min.)").fill("PasswordA123");
  await page.getByPlaceholder("Confirmer le mot de passe").fill("PasswordB456");
  await page.getByRole("button", { name: "Définir le mot de passe" }).click();

  await expect(page.getByText("Les deux mots de passe ne correspondent pas.")).toBeVisible();
});
