// `NEXT_PUBLIC_API_URL` explicitement fourni (Docker build --build-arg, .env local, CI) est
// toujours prioritaire, ici et dans `headers()` ci-dessous — jamais remplacé. Absent, ce repli
// utilise l'API locale déjà documentée partout ailleurs dans ce projet (.env.example,
// docs/deployment/PRODUCTION_CONFIGURATION.md, lib/api/client.ts) — jamais un domaine inventé
// (l'ancien repli "https://api.edulinkage.com" ne correspondait à aucun hébergeur réel et cassait
// silencieusement toute connexion locale non explicitement configurée — voir
// docs/phases/PHASE_28A_PARENT_WEB_PORTAL.md pour l'incident que ce repli a provoqué).
//
// En production (`next build`/`next start`, où Next.js force NODE_ENV=production), une variable
// manquante déclenche un avertissement de build, jamais un échec : `next build`/`next lint`
// tournent aussi en CI (.github/workflows/ci.yml, job "web") sans jamais définir cette variable —
// un échec bloquant casserait la CI pour une raison sans rapport avec le code testé. Même
// sévérité que `EMAIL_PROVIDER=local` en production côté backend (avertir, pas refuser — voir
// apps/api/app/core/config.py::validate_production_config) : une URL d'API pointant par erreur
// vers localhost casse l'app de façon immédiatement visible pour quiconque l'utilise, ce n'est
// pas un risque silencieux à bloquer au build comme le serait un secret JWT/DB par défaut.
const isProduction = process.env.NODE_ENV === "production";
const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL;

if (isProduction && !configuredApiUrl) {
  console.warn(
    "[next.config.js] NEXT_PUBLIC_API_URL n'est pas défini pour ce build de production — " +
      "repli sur http://localhost:8000 (voir docs/deployment/PRODUCTION_CONFIGURATION.md). " +
      "Ne jamais déployer ce build tel quel en pilote/production réel.",
  );
}

const resolvedApiUrl = configuredApiUrl || "http://localhost:8000";

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

module.exports = nextConfig;
