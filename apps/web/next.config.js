// `NEXT_PUBLIC_API_URL` est FIGÉE dans le bundle client au moment de `next build`.
//
// Risque H1 (audit final School Cashier Lot 3) — avant ce correctif, une variable absente ne
// produisait qu'un avertissement et un build "réussi" pointant vers http://localhost:8000 depuis le
// navigateur de chaque utilisateur. Désormais (voir config/apiUrl.js pour les règles exactes) :
// - `next build` (phase PRODUCTION_BUILD, hors `next lint`) : validation STRICTE — variable
//   absente, vide, mal formée ou locale (localhost, 127.x, ::1, 0.0.0.0) => le build ÉCHOUE ;
// - build non déployable (CI, validations e2e jetables) : drapeau EXPLICITE
//   EDULINKAGE_NON_DEPLOYABLE_BUILD=1 (jamais transmis par apps/web/Dockerfile) => repli local
//   autorisé, avec avertissement ;
// - `next dev`, `next start`, `next lint` : comportement inchangé (repli local, jamais d'échec) —
//   `next lint` charge la configuration dans la même phase que `next build` (CI sans variable).
// Jamais un domaine inventé (voir docs/phases/PHASE_28A_PARENT_WEB_PORTAL.md).
const { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } = require("next/constants");
const { resolveApiUrl } = require("./config/apiUrl");
const { resolveAnalytics } = require("./config/analytics");

function isStrictBuild(phase) {
  return phase === PHASE_PRODUCTION_BUILD && !process.argv.includes("lint");
}

function createNextConfig(resolvedApiUrl, phase, analytics = resolveAnalytics(process.env)) {
  /** @type {import('next').NextConfig} */
  const nextConfig = {
    reactStrictMode: true,

    // 2026-11-17 (revue de sécurité) — ne plus annoncer « X-Powered-By: Next.js » : inutile au site,
    // utile à un attaquant qui cherche les failles d'une version précise.
    poweredByHeader: false,

    // 2026-11-17 (revue de sécurité) — l'optimiseur d'images (/_next/image) n'est plus utilisé : le
    // site n'affiche que ses propres logos, déjà à la bonne taille. Les failles graves connues de cet
    // optimiseur (exécution de code à distance via des images piégées, corrigées seulement à partir de
    // Next.js 15.5) ne concernent plus le site. Les images sont servies telles quelles.
    images: {
      unoptimized: true,
    },

    env: {
      NEXT_PUBLIC_API_URL: resolvedApiUrl,
      // 2026-11-24 — mesure d'audience Umami (config/analytics.js) : vides = aucune mesure, aucun bandeau.
      NEXT_PUBLIC_UMAMI_SRC: analytics ? analytics.src : "",
      NEXT_PUBLIC_UMAMI_WEBSITE_ID: analytics ? analytics.websiteId : "",
    },

    // Phase 26.2 — CSP d'abord en Report-Only (observation seulement).
    // 2026-11-17 (revue de sécurité) — CSP désormais BLOQUANTE. Elle ferme ce qui permettrait à un
    // script injecté d'envoyer la session ailleurs ou d'habiller une autre page : appels réseau
    // limités au site et à l'API (connect-src), images au site (img-src), formulaires au site
    // (form-action), aucun plugin (object-src), aucune mise en cadre (frame-ancestors), aucun
    // changement de <base>. Scripts et styles « inline » restent permis : Next.js 14 en insère dans
    // chaque page (données de rendu), et une politique par nonce imposerait un rendu dynamique de
    // toutes les pages, incompatible avec les pages gardées hors connexion (Phase 32). En
    // développement seulement, 'unsafe-eval' (rechargement à chaud de Next.js).
    async headers() {
      const apiOrigin = resolvedApiUrl;
      const devEval = phase === PHASE_DEVELOPMENT_SERVER ? " 'unsafe-eval'" : "";
      // 2026-11-24 — Umami (s'il est configuré) : son script (script-src) et l'envoi des visites (connect-src),
      // depuis la seule origine du serveur de mesure. Rien d'autre n'est ouvert.
      const analyticsOrigin = analytics ? ` ${analytics.origin}` : "";
      const csp = [
        "default-src 'self'",
        `script-src 'self' 'unsafe-inline'${devEval}${analyticsOrigin}`,
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        `connect-src 'self' ${apiOrigin}${analyticsOrigin}`,
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join("; ");

      return [
        // Phase 32 — le service worker (généré par scripts/generate-sw.mjs) est relu à chaque
        // vérification : une nouvelle version du site est ainsi détectée dès qu'elle est en ligne.
        {
          source: "/sw.js",
          headers: [{ key: "Cache-Control", value: "no-cache" }],
        },
        {
          source: "/:path*",
          headers: [
            {
              key: "Content-Security-Policy",
              value: csp,
            },
            // Phase 26.2 (suite) — headers de sécurité de base, déjà présents côté API (voir
            // app/main.py::security_headers_middleware) mais absents côté Web jusqu'ici. Aucune
            // fonctionnalité de l'app n'utilise géolocalisation/caméra/micro/Payment Request API
            // (vérifié par grep avant ce changement) : la politique Permissions-Policy ci-dessous
            // ne restreint donc rien d'actuellement utilisé.
            {
              key: "X-Content-Type-Options",
              value: "nosniff",
            },
            {
              key: "X-Frame-Options",
              value: "DENY",
            },
            {
              key: "Referrer-Policy",
              value: "strict-origin-when-cross-origin",
            },
            {
              key: "Permissions-Policy",
              value: "camera=(), microphone=(), geolocation=(), payment=()",
            },
          ],
        },
      ];
    },
  };

  return nextConfig;
}

module.exports = (phase) => {
  const { url, warnings } = resolveApiUrl({ env: process.env, strict: isStrictBuild(phase) });
  for (const warning of warnings) console.warn(`[next.config.js] ${warning}`);
  return createNextConfig(url, phase);
};
