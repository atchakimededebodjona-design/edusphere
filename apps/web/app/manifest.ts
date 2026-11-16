import type { MetadataRoute } from "next";

// Phase 32, lot 1 — manifeste de l'application installable (servi en /manifest.webmanifest).
// Démarrage sur /dashboard : AuthGate y envoie chaque compte vers son espace (parent, enseignant,
// partenaire) ou vers la connexion. Icônes : symbole officiel redimensionné (public/icons/), jamais
// redessiné.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "EduLinkage",
    short_name: "EduLinkage",
    description: "Gestion scolaire EduLinkage, consultable même sans connexion.",
    lang: "fr",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#0B1224",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
