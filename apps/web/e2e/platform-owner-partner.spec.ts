import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync, unlinkSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { expect, test } from "@playwright/test";

// PR #17 — routage des espaces Propriétaire de la plateforme / Partenaire. Ces tests vérifient la
// NAVIGATION uniquement (redirections, menus) : ce n'est pas une frontière de sécurité, la
// protection réelle est couverte côté API (apps/api/tests/test_platform_owner.py,
// test_partners.py, test_partner_isolation.py). Le compte PLATFORM_OWNER n'a, par conception, aucun
// flux produit de création : reproduit ici directement en base, même mécanisme que
// platform-admin.spec.ts.
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const COMPOSE_PROJECT_NAME = process.env.COMPOSE_PROJECT_NAME ?? "edusphere";
const PASSWORD = "SuperSecret123";

let uniqueCounter = 0;
function unique(prefix: string): string {
  uniqueCounter += 1;
  return `${prefix}${Date.now()}${uniqueCounter}${Math.floor(Math.random() * 10000)}`;
}

function runInApiContainer(script: string): void {
  const tmpFile = path.join(os.tmpdir(), `platform_owner_${unique("e2e")}.py`);
  writeFileSync(tmpFile, script, "utf-8");
  const containerPath = `/app/platform_owner_e2e_${unique("")}.py`;
  try {
    execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "cp", tmpFile, `api:${containerPath}`], {
      cwd: REPO_ROOT,
    });
    try {
      execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "python", containerPath], {
        cwd: REPO_ROOT,
      });
    } finally {
      try {
        execFileSync("docker", ["compose", "-p", COMPOSE_PROJECT_NAME, "exec", "-T", "api", "rm", "-f", containerPath], {
          cwd: REPO_ROOT,
        });
      } catch {
        // Best-effort.
      }
    }
  } finally {
    unlinkSync(tmpFile);
  }
}

function createPlatformOwnerAccount(email: string): void {
  const userId = randomUUID();
  runInApiContainer(
    [
      "import asyncio, uuid",
      "from sqlalchemy import select",
      "from app.db import model_registry  # noqa: F401",
      "from app.core.security import hash_password",
      "from app.core.tenancy import set_platform_wide_context",
      "from app.db.session import AsyncSessionLocal",
      "from app.modules.rbac.models import Role, UserRole",
      "from app.modules.users.models import User",
      "",
      "async def main():",
      "    async with AsyncSessionLocal() as db:",
      "        await set_platform_wide_context(db)",
      `        db.add(User(id=uuid.UUID(${JSON.stringify(userId)}), email=${JSON.stringify(email)},`,
      `            full_name="Platform Owner E2E", hashed_password=hash_password(${JSON.stringify(PASSWORD)}),`,
      "            is_active=True, is_platform_admin=True))",
      "        await db.flush()",
      '        role = (await db.execute(select(Role).where(Role.code == "PLATFORM_OWNER"))).scalar_one()',
      `        db.add(UserRole(id=uuid.uuid4(), user_id=uuid.UUID(${JSON.stringify(userId)}), role_id=role.id,`,
      "            organization_id=None, school_id=None))",
      "        await db.commit()",
      "",
      "asyncio.run(main())",
    ].join("\n"),
  );
}

async function login(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

test("propriétaire de la plateforme : accueil et menu plateforme uniquement, création d'un partenaire, puis espace partenaire", async ({
  page,
  request,
}) => {
  const ownerEmail = `${unique("owner").toLowerCase()}@platform-e2e.example`;
  createPlatformOwnerAccount(ownerEmail);

  await login(page, ownerEmail);
  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByRole("heading", { name: "Administration de la plateforme" })).toBeVisible();
  const nav = page.locator("nav");
  await expect(nav.getByRole("link", { name: "Partenaires" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Établissements" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Élèves" })).toHaveCount(0);

  // Une URL scolaire tapée à la main renvoie vers l'espace plateforme (navigation seulement).
  await page.goto("/students");
  await expect(page).toHaveURL("/dashboard");
  await page.goto("/platform/schools");
  await expect(page.getByRole("heading", { name: "Écoles" })).toBeVisible();

  // Création d'un partenaire via l'écran plateforme.
  const partnerEmail = `${unique("partner").toLowerCase()}@platform-e2e.example`;
  await nav.getByRole("link", { name: "Partenaires" }).click();
  await expect(page).toHaveURL("/platform/partners");
  await page.getByPlaceholder("Nom du partenaire").fill("Agence E2E");
  await page.getByPlaceholder("Nom du contact").fill("Contact E2E");
  await page.getByPlaceholder("Email du contact").fill(partnerEmail);
  await page.getByRole("button", { name: "Créer le partenaire" }).click();
  await expect(page.getByText("Partenaire « Agence E2E » créé.", { exact: false })).toBeVisible();

  // Activation du compte partenaire (jeton dev, jamais exposé en production) via l'API.
  const ownerLogin = await request.post(`${API_BASE_URL}/api/v1/auth/login`, {
    data: { email: ownerEmail, password: PASSWORD },
  });
  const ownerToken = (await ownerLogin.json()).access_token as string;
  const secondPartnerEmail = `${unique("partner2").toLowerCase()}@platform-e2e.example`;
  const created = await request.post(`${API_BASE_URL}/api/v1/platform/partners`, {
    headers: { Authorization: `Bearer ${ownerToken}` },
    data: { display_name: "Agence E2E 2", full_name: "Contact E2E 2", email: secondPartnerEmail },
  });
  expect(created.status()).toBe(201);
  const reset = await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: (await created.json()).dev_reset_token, new_password: PASSWORD },
  });
  expect(reset.status()).toBe(204);

  // Espace partenaire : redirection vers /partner, menu partenaire uniquement.
  await page.context().clearCookies();
  await page.evaluate(() => window.localStorage.clear());
  await login(page, secondPartnerEmail);
  await expect(page).toHaveURL("/partner");
  await expect(page.getByRole("heading", { name: "Espace partenaire" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Mes écoles" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Partenaires" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Élèves" })).toHaveCount(0);

  // Une URL de l'espace école tapée à la main renvoie vers /partner (navigation seulement — l'API
  // refuse de toute façon ces données à ce compte).
  await page.goto("/students");
  await expect(page).toHaveURL("/partner");
  await page.goto("/platform/partners");
  await expect(page).toHaveURL("/partner");
  await page.goto("/partner/schools");
  await expect(page.getByRole("heading", { name: "Mes écoles" })).toBeVisible();
  await expect(page.getByText("Aucune école inscrite pour le moment.")).toBeVisible();
});
