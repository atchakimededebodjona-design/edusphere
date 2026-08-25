import { expect, test } from "@playwright/test";

test("unauthenticated visitor to / is redirected to /login, not a static placeholder", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();
});

test("register page renders the school signup form", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Inscrire mon école" })).toBeVisible();
  await expect(page.getByPlaceholder("Nom de l'organisation")).toBeVisible();
  await expect(page.getByPlaceholder("Votre email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer mon compte" })).toBeVisible();
});

test("login page renders and rejects bad credentials with a visible error", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill("nobody@example-does-not-exist.tg");
  await page.getByPlaceholder("Mot de passe").fill("wrong-password");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText(/erreur|invalid|incorrect/i)).toBeVisible({ timeout: 10_000 });
});
