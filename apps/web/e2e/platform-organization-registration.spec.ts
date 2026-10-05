import { expect, test } from "@playwright/test";
import {
  createOrganizationViaPlatform,
  createPlatformAdminAccount,
  loginInBrowser,
  registerOrgAdminInBrowser,
  TENANT_PASSWORD,
  unique,
} from "./helpers/tenants";

// Inscription d'une organisation réservée à l'administrateur de la plateforme. Le contrôle réel est
// côté backend (POST /api/v1/platform/organizations, require_platform_admin) : ces tests vérifient
// aussi l'interface, mais la protection frontend n'est qu'un complément.

const NEW_ORG_PATH = "/dashboard/organizations/new";
const REGISTER_LABEL = /inscri|créer un compte|s'inscrire/i;

async function loginAsPlatformAdmin(page: import("@playwright/test").Page): Promise<void> {
  const email = `${unique("platformorg").toLowerCase()}@platform-e2e.example`;
  createPlatformAdminAccount(email, TENANT_PASSWORD);
  await loginInBrowser(page, email, TENANT_PASSWORD);
  await expect(page.getByRole("heading", { name: "Administration de la plateforme" })).toBeVisible();
}

test("administrateur de plateforme : voit le bouton « + Inscrire une organisation » sur le tableau de bord", async ({
  page,
}) => {
  await loginAsPlatformAdmin(page);

  const button = page.getByRole("link", { name: "+ Inscrire une organisation" });
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute("href", NEW_ORG_PATH);
});

test("School Admin : ne voit pas le bouton d'inscription d'organisation", async ({ page, request }) => {
  const tenant = await createOrganizationViaPlatform(request, "orgbtnhidden");
  await loginInBrowser(page, tenant.orgAdminEmail, tenant.password);

  await expect(page.getByRole("link", { name: "+ Inscrire une organisation" })).toHaveCount(0);
});

test("administrateur de plateforme : accède à la page de création", async ({ page }) => {
  await loginAsPlatformAdmin(page);
  await page.goto(NEW_ORG_PATH);

  await expect(page.getByRole("heading", { name: "Inscrire une organisation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer l'organisation" })).toBeVisible();
});

test("School Admin : la page de création le renvoie vers son tableau de bord", async ({ page, request }) => {
  const tenant = await createOrganizationViaPlatform(request, "orgpagegate");
  await loginInBrowser(page, tenant.orgAdminEmail, tenant.password);

  await page.goto(NEW_ORG_PATH);
  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByRole("heading", { name: "Inscrire une organisation" })).toHaveCount(0);
});

test("formulaire : les champs obligatoires affichent des erreurs sans appel API", async ({ page }) => {
  await loginAsPlatformAdmin(page);
  await page.goto(NEW_ORG_PATH);

  await page.getByRole("button", { name: "Créer l'organisation" }).click();
  await expect(page.getByText("Le nom de l'organisation est obligatoire")).toBeVisible();
  await expect(page.getByText("Adresse email valide requise.")).toBeVisible();
  await expect(page).toHaveURL(NEW_ORG_PATH);
});

test("formulaire : confirmation de mot de passe différente refusée", async ({ page }) => {
  await loginAsPlatformAdmin(page);
  await page.goto(NEW_ORG_PATH);

  await page.getByLabel("Mot de passe initial").fill("SuperSecret123");
  await page.getByLabel("Confirmation du mot de passe").fill("AutreMotDePasse1");
  await page.getByRole("button", { name: "Créer l'organisation" }).click();
  await expect(page.getByText("La confirmation ne correspond pas au mot de passe.")).toBeVisible();
});

test("création réussie : affiche l'organisation, l'école et l'administrateur, sans connecter le School Admin", async ({
  page,
}) => {
  await loginAsPlatformAdmin(page);
  await page.goto(NEW_ORG_PATH);

  const slug = unique("orgcreated").toLowerCase();
  const adminEmail = `${slug}-admin@platform-e2e.example`;
  await page.getByLabel("Nom de l'organisation").fill(`Org ${slug}`);
  await page.getByLabel("Slug").first().fill(slug);
  await page.getByLabel("Nom de l'école").fill(`Ecole ${slug}`);
  await page.getByLabel("Slug").nth(1).fill("principale");
  await page.getByLabel("Nom complet").fill("Admin Création");
  await page.getByLabel("Email").last().fill(adminEmail);
  await page.getByLabel("Mot de passe initial").fill(TENANT_PASSWORD);
  await page.getByLabel("Confirmation du mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Créer l'organisation" }).click();

  await expect(page.getByRole("heading", { name: "Organisation créée avec succès" })).toBeVisible();
  await expect(page.getByText(`Org ${slug}`)).toBeVisible();
  await expect(page.getByText(adminEmail)).toBeVisible();
  // Le platform admin reste connecté sur son propre espace : aucune bascule de session.
  await expect(page.getByRole("link", { name: "Retour au tableau de bord" })).toBeVisible();
});

test("conflit de slug : message utilisateur compréhensible (409)", async ({ page, request }) => {
  const existing = await createOrganizationViaPlatform(request, "orgdup");
  await loginAsPlatformAdmin(page);
  await page.goto(NEW_ORG_PATH);

  await page.getByLabel("Nom de l'organisation").fill("Org doublon");
  await page.getByLabel("Slug").first().fill(existing.slug);
  await page.getByLabel("Nom de l'école").fill("Ecole doublon");
  await page.getByLabel("Slug").nth(1).fill("principale");
  await page.getByLabel("Nom complet").fill("Admin Doublon");
  await page.getByLabel("Email").last().fill(`${unique("dupadmin").toLowerCase()}@platform-e2e.example`);
  await page.getByLabel("Mot de passe initial").fill(TENANT_PASSWORD);
  await page.getByLabel("Confirmation du mot de passe").fill(TENANT_PASSWORD);
  await page.getByRole("button", { name: "Créer l'organisation" }).click();

  await expect(
    page.getByText("Ce slug d'organisation ou cet email administrateur est déjà utilisé.", { exact: true }),
  ).toBeVisible();
});

test("page de connexion : aucun bouton ni lien d'inscription", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();

  await expect(page.getByRole("link", { name: REGISTER_LABEL })).toHaveCount(0);
  await expect(page.getByRole("button", { name: REGISTER_LABEL })).toHaveCount(0);
});

test("un School Admin connecté via /login arrive sur son tableau de bord", async ({ page }) => {
  await registerOrgAdminInBrowser(page, "orgloginflow");
  await expect(page).toHaveURL("/dashboard");
});
