/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || "https://api.edulinkage.com",
  },

  // Phase 26.2 — CSP en mode Report-Only uniquement. L'app n'utilise ni police externe, ni
  // script tiers, ni iframe, ni style inline (vérifié par grep sur next/font, <script src=,
  // style={{ avant ce changement) — mais aucun build de production réel n'a pu être observé
  // dans un navigateur pendant cette phase (pas d'accès VPS pour redéployer). Report-Only ne
  // bloque jamais aucune ressource : elle sert uniquement à observer, via la console du
  // navigateur, si cette politique casserait quelque chose avant de l'activer en mode bloquant
  // (Phase 26.3, après revue des violations réelles).
  async headers() {
    const apiOrigin = process.env.NEXT_PUBLIC_API_URL || "https://api.edulinkage.com";
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
