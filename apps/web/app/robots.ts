import type { MetadataRoute } from "next";

// 2026-11-24 — robots.txt : seules les pages publiques sont à indexer. Les espaces connectés et les
// liens personnels (définition du mot de passe, vérification d'un bulletin) sont exclus ; leurs pages
// portent aussi « noindex ».
const PRIVATE_PATHS = [
  "/dashboard",
  "/students",
  "/attendance",
  "/grades",
  "/report-cards",
  "/announcements",
  "/notifications",
  "/users",
  "/school",
  "/academics",
  "/setup",
  "/promotions",
  "/audit-logs",
  "/fees",
  "/payments",
  "/cashier",
  "/subscription",
  "/platform",
  "/partner",
  "/teacher",
  "/parent",
  "/reset-password",
  "/verify",
  "/offline",
  "/open-notifications",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: PRIVATE_PATHS }],
    sitemap: "https://edulinkage.com/sitemap.xml",
    host: "https://edulinkage.com",
  };
}
