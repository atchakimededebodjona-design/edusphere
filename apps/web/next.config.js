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
const { PHASE_PRODUCTION_BUILD } = require("next/constants");
const { resolveApiUrl } = require("./config/apiUrl");

function isStrictBuild(phase) {
  return phase === PHASE_PRODUCTION_BUILD && !process.argv.includes("lint");
}

function createNextConfig(resolvedApiUrl) {
  /** @type {import('next').NextConfig} */
  const nextConfig = {
    reactStrictMode: true,

    env: {
      NEXT_PUBLIC_API_URL: resolvedApiUrl,
    },

    // Phase 26.2 — CSP en mode Report-Only uniquement. L'app n'utilise ni police externe, ni
    // script tiers, ni iframe, ni style inline (vérifié par grep sur next/font, <script src=,
    // style={{ avant ce changement) — mais aucun build de production réel n'a pu être observé
    // dans un navigateur pendant cette phase (pas d'accès VPS pour redéployer). Report-Only ne
    // bloque jamais aucune ressource : elle sert uniquement à observer, via la console du
    // navigateur, si cette politique casserait quelque chose avant de l'activer en mode bloquant
    // (Phase 26.3, après revue des violations réelles).
    async headers() {
      const apiOrigin = resolvedApiUrl;
      const csp = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        `connect-src 'self' ${apiOrigin}`,
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join("; ");

      return [
        {
          source: "/:path*",
          headers: [
            {
              key: "Content-Security-Policy-Report-Only",
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
  return createNextConfig(url);
};
