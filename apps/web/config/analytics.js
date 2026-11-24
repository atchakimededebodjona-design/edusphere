// Mesure d'audience Umami (2026-11-24, choix de l'exploitant : Umami hébergé sur son propre serveur).
//
// Deux variables FIGÉES au build (NEXT_PUBLIC_*), toutes deux nécessaires :
// - NEXT_PUBLIC_UMAMI_SRC : adresse du script, ex. https://stats.edulinkage.com/script.js ;
// - NEXT_PUBLIC_UMAMI_WEBSITE_ID : identifiant du site dans Umami (UUID).
// Les deux absentes : aucune mesure, aucun bandeau, CSP inchangée. Une seule renseignée, ou une valeur
// invalide : le build ÉCHOUE (une mesure à moitié configurée serait silencieusement morte). L'origine du
// script est ajoutée à la CSP (script-src pour le charger, connect-src pour l'envoi des visites).
//
// Module CommonJS pur (aucune dépendance) : utilisé par next.config.js, testé par config/analytics.test.js.

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isLocalHostname(hostname) {
  return hostname === "localhost" || /^127(\.\d{1,3}){3}$/.test(hostname);
}

/** @returns {{ src: string, websiteId: string, origin: string } | null} */
function resolveAnalytics(env) {
  const src = (env.NEXT_PUBLIC_UMAMI_SRC || "").trim();
  const websiteId = (env.NEXT_PUBLIC_UMAMI_WEBSITE_ID || "").trim();
  if (!src && !websiteId) return null;
  if (!src || !websiteId) {
    throw new Error(
      "Mesure d'audience : NEXT_PUBLIC_UMAMI_SRC et NEXT_PUBLIC_UMAMI_WEBSITE_ID vont ensemble (renseigner les deux, ou aucune).",
    );
  }
  let url;
  try {
    url = new URL(src);
  } catch {
    throw new Error(`Mesure d'audience : NEXT_PUBLIC_UMAMI_SRC n'est pas une adresse valide (${src}).`);
  }
  // HTTPS obligatoire, sauf serveur local (vérifications automatiques sur la machine de développement).
  const allowedProtocol = url.protocol === "https:" || (url.protocol === "http:" && isLocalHostname(url.hostname));
  if (!allowedProtocol || url.username || url.password || url.search || url.hash) {
    throw new Error(`Mesure d'audience : NEXT_PUBLIC_UMAMI_SRC doit être une adresse https simple (${src}).`);
  }
  if (!UUID_PATTERN.test(websiteId)) {
    throw new Error("Mesure d'audience : NEXT_PUBLIC_UMAMI_WEBSITE_ID doit être l'identifiant (UUID) du site dans Umami.");
  }
  return { src: url.toString(), websiteId: websiteId.toLowerCase(), origin: url.origin };
}

module.exports = { resolveAnalytics };
