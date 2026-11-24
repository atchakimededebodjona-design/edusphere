import type { MetadataRoute } from "next";

// 2026-11-24 — plan du site pour les moteurs de recherche : uniquement les pages publiques.
const BASE = "https://edulinkage.com";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${BASE}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/login`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
