// Phase 32, lot 1 — produit `public/sw.js` après `next build` (voir le script `build` de
// package.json) : le modèle `sw/service-worker.js`, précédé de la version du build et de la liste
// des fichiers du site à garder sur l'appareil (code, styles, pages sans identifiant, fichiers de
// `public/`). Aucune dépendance : seulement les fichiers que `next build` vient d'écrire.

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SW_FILE = "sw.js";

// Pages jamais gardées : la page 404 interne de Next.js.
const EXCLUDED_ROUTES = new Set(["/_not-found"]);

// Indépendant du système qui construit (Windows en local, Linux dans Docker et la CI).
function toUrlPath(path) {
  return path.replace(/\\/g, "/");
}

function listFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...listFiles(full));
    else out.push(full);
  }
  return out;
}

/**
 * Liste triée et dédoublonnée des URL à garder. Fonction pure, testée par generate-sw.test.mjs.
 * @param {{ routes: string[], staticFiles: string[], publicFiles: string[] }} input
 *   routes : clés de `.next/prerender-manifest.json` ; staticFiles : chemins relatifs à
 *   `.next/static` ; publicFiles : chemins relatifs à `public/`.
 */
export function buildPrecacheList({ routes, staticFiles, publicFiles }) {
  const urls = new Set();
  for (const route of routes) {
    if (!route.startsWith("/") || EXCLUDED_ROUTES.has(route) || route.endsWith(".rsc")) continue;
    urls.add(route);
  }
  for (const file of staticFiles) urls.add(`/_next/static/${toUrlPath(file)}`);
  for (const file of publicFiles) {
    const url = `/${toUrlPath(file)}`;
    // Fichiers cachés (.gitkeep…) : jamais utiles au site, et un seul fichier non servi ferait
    // échouer toute l'installation.
    if (url === `/${SW_FILE}` || url.split("/").some((part) => part.startsWith("."))) continue;
    urls.add(url);
  }
  return [...urls].sort();
}

export function renderServiceWorker({ version, precache, template }) {
  if (!/^[A-Za-z0-9_-]+$/.test(version)) throw new Error(`Identifiant de build inattendu : ${version}`);
  const config = JSON.stringify({ version, precache });
  return `// Fichier GÉNÉRÉ par scripts/generate-sw.mjs — ne pas modifier ni versionner.\nself.__EDULINKAGE_SW__ = ${config};\n${template}`;
}

function main() {
  const webDir = fileURLToPath(new URL("..", import.meta.url));
  const nextDir = join(webDir, ".next");
  const publicDir = join(webDir, "public");

  const version = readFileSync(join(nextDir, "BUILD_ID"), "utf8").trim();
  const prerender = JSON.parse(readFileSync(join(nextDir, "prerender-manifest.json"), "utf8"));
  const staticDir = join(nextDir, "static");
  const precache = buildPrecacheList({
    routes: Object.keys(prerender.routes ?? {}),
    staticFiles: listFiles(staticDir).map((file) => relative(staticDir, file)),
    publicFiles: listFiles(publicDir).map((file) => relative(publicDir, file)),
  });
  if (!precache.includes("/offline")) throw new Error("La page /offline doit être statique et gardée.");

  const template = readFileSync(join(webDir, "sw", "service-worker.js"), "utf8");
  writeFileSync(join(publicDir, SW_FILE), renderServiceWorker({ version, precache, template }));
  console.log(`[generate-sw] public/${SW_FILE} : version ${version}, ${precache.length} fichiers gardés hors connexion.`);
}

// Écrit seulement sur demande explicite (script `build`) : l'import par les tests n'écrit rien.
if (process.argv.includes("--write")) main();
