// Validation de NEXT_PUBLIC_API_URL (risque H1, audit final School Cashier Lot 3).
//
// La valeur est FIGÉE dans le bundle client au moment de `next build` (variable NEXT_PUBLIC_*) :
// une URL absente ou locale produisait jusqu'ici un build "réussi" (simple avertissement) qui
// appelait http://localhost:8000 depuis le navigateur de chaque utilisateur. Un build de
// production doit désormais ÉCHOUER dans ces cas.
//
// Module CommonJS pur (aucune dépendance) : utilisé par next.config.js et testé par
// config/apiUrl.test.js (`node --test`).

const DEV_FALLBACK_API_URL = "http://localhost:8000";

// Échappatoire EXPLICITE pour les builds non déployables (CI, validations e2e jetables), qui n'ont
// pas d'API publique : autorise une URL locale/absente. Jamais transmise par apps/web/Dockerfile
// (aucun ARG) : un build d'image ne peut pas l'utiliser par accident.
const NON_DEPLOYABLE_FLAG = "EDULINKAGE_NON_DEPLOYABLE_BUILD";

function isLocalHostname(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    /^127(\.\d{1,3}){3}$/.test(host) ||
    host === "0.0.0.0" ||
    host === "::1" ||
    host === "::" ||
    host === "0:0:0:0:0:0:0:1"
  );
}

/**
 * Valide la valeur destinée à un build de PRODUCTION.
 * @param {string | undefined} raw valeur brute de NEXT_PUBLIC_API_URL
 * @returns {{ ok: true, url: string, warnings: string[] } | { ok: false, error: string }}
 */
function validateProductionApiUrl(raw) {
  const value = typeof raw === "string" ? raw.trim() : "";
  if (!value) {
    return { ok: false, error: "NEXT_PUBLIC_API_URL est absente ou vide." };
  }
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return { ok: false, error: `NEXT_PUBLIC_API_URL n'est pas une URL valide : "${value}".` };
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, error: `NEXT_PUBLIC_API_URL doit utiliser http(s), reçu "${parsed.protocol}".` };
  }
  if (parsed.username || parsed.password) {
    return { ok: false, error: "NEXT_PUBLIC_API_URL ne doit contenir aucun identifiant (elle est publique dans le bundle)." };
  }
  if (parsed.search || parsed.hash) {
    return { ok: false, error: "NEXT_PUBLIC_API_URL ne doit contenir ni paramètres (?) ni fragment (#)." };
  }
  if (value.endsWith("/")) {
    // lib/api/client.ts concatène `${API_URL}/api/v1/...` : une barre finale produirait "//api".
    return { ok: false, error: "NEXT_PUBLIC_API_URL ne doit pas se terminer par « / »." };
  }
  if (isLocalHostname(parsed.hostname)) {
    return {
      ok: false,
      error: `NEXT_PUBLIC_API_URL pointe vers une adresse locale (${parsed.hostname}) : inutilisable depuis le navigateur d'un utilisateur.`,
    };
  }
  const warnings = [];
  if (parsed.protocol === "http:") {
    // Non bloquant (décision documentée, à réévaluer) : la production publique vérifiée le
    // 2026-10-18 utilise https://api.edulinkage.com (TLS valide, HSTS, http -> 301 https), mais
    // aucun inventaire des autres environnements (pilote, préproduction) n'existe dans ce dépôt ;
    // bloquer http pourrait casser l'un d'eux. Risque réel d'une API en http : jetons d'accès et
    // données d'élèves/paiements en clair sur le réseau — voir
    // docs/deployment/PRODUCTION_CONFIGURATION.md, section HTTPS.
    warnings.push(
      "NEXT_PUBLIC_API_URL utilise http:// (non chiffré) : jetons et données transitent en clair. " +
        "Utiliser https:// (la production publique est en HTTPS).",
    );
  }
  return { ok: true, url: value, warnings };
}

/**
 * URL à figer dans le build. `next build` déployable : validation stricte (exception si invalide).
 * Builds non déployables (drapeau explicite), `next dev`, `next start`, `next lint` : repli local.
 * @param {{ env: Record<string, string | undefined>, strict: boolean }} options
 * @returns {{ url: string, warnings: string[] }}
 */
function resolveApiUrl({ env, strict }) {
  const raw = env.NEXT_PUBLIC_API_URL;
  const nonDeployable = env[NON_DEPLOYABLE_FLAG] === "1" || env[NON_DEPLOYABLE_FLAG] === "true";
  if (strict && !nonDeployable) {
    const result = validateProductionApiUrl(raw);
    if (!result.ok) {
      throw new Error(
        `[next.config.js] Build de production refusé : ${result.error} ` +
          "Définissez NEXT_PUBLIC_API_URL avec l'URL PUBLIQUE de l'API (ex. https://api.<votre-domaine>) " +
          `— voir docs/deployment/PRODUCTION_CONFIGURATION.md. Build non déployable (CI, e2e local) : ${NON_DEPLOYABLE_FLAG}=1.`,
      );
    }
    return { url: result.url, warnings: result.warnings };
  }
  const value = typeof raw === "string" && raw.trim() ? raw.trim() : DEV_FALLBACK_API_URL;
  const warnings = strict
    ? [`${NON_DEPLOYABLE_FLAG}=1 : build NON DÉPLOYABLE (API ${value}). Ne jamais publier ce build.`]
    : [];
  return { url: value, warnings };
}

module.exports = { DEV_FALLBACK_API_URL, NON_DEPLOYABLE_FLAG, isLocalHostname, validateProductionApiUrl, resolveApiUrl };
