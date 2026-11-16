/* EduLinkage — service worker (Phase 32, lot 1 : application installable, consultable hors connexion).
 *
 * Modèle : `scripts/generate-sw.mjs` le copie dans `public/sw.js` après `next build`, précédé de
 * `self.__EDULINKAGE_SW__ = { version, precache }` (identifiant du build + liste des fichiers du site).
 * `public/sw.js` est un fichier généré : ne jamais le modifier ni le versionner.
 *
 * Ce que ce fichier garde sur l'appareil : uniquement le SITE (code, styles, pages, images du site).
 * Jamais une donnée d'école : l'API (autre origine) n'est pas interceptée ici ; ses réponses sont
 * gardées par compte par l'application elle-même (lib/offline/responseCache.ts) et effacées à la
 * déconnexion.
 */
/* eslint-disable */

const CONFIG = self.__EDULINKAGE_SW__;
const PRECACHE = "edulinkage-precache-" + CONFIG.version;
const PAGES_PREFIX = "edulinkage-pages-";
const PAGES = PAGES_PREFIX + CONFIG.version; // pages à identifiant (fiche élève…) ouvertes avec internet
const ASSETS = "edulinkage-assets"; // images optimisées par Next.js
const OFFLINE_PAGE = "/offline";
const PRECACHED = new Set(CONFIG.precache);
const MAX_PAGES = 150;
const MAX_ASSETS = 80;
const PARALLEL_DOWNLOADS = 6;

// --- Installation : tout le site est téléchargé une fois (environ 0,6 Mo compressé) -------------------
self.addEventListener("install", (event) => {
  event.waitUntil(precacheAll().then(() => self.skipWaiting()));
});

async function precacheAll() {
  const cache = await caches.open(PRECACHE);
  const queue = CONFIG.precache.slice();
  async function worker() {
    while (queue.length > 0) {
      const url = queue.shift();
      if (await cache.match(url)) continue; // reprise d'une installation interrompue
      if (url.startsWith("/_next/static/")) {
        // Fichiers immuables (nom = empreinte du contenu) : repris d'une version précédente si présents.
        const previous = await caches.match(url);
        if (previous) {
          await cache.put(url, previous);
          continue;
        }
      }
      await cache.put(url, await fetchForCache(url));
    }
  }
  // Un seul fichier manquant fait échouer l'installation : le navigateur la retentera plus tard, et
  // l'ancienne version (ou le site en ligne) reste utilisée en attendant.
  await Promise.all(Array.from({ length: PARALLEL_DOWNLOADS }, worker));
}

async function fetchForCache(url, attempt = 0) {
  try {
    const response = await fetch(url, { cache: "reload", credentials: "same-origin" });
    if (!response.ok) throw new Error(url + " : HTTP " + response.status);
    return response.redirected ? cleanCopy(response) : response;
  } catch (err) {
    if (attempt < 2) return fetchForCache(url, attempt + 1);
    throw err;
  }
}

// Une réponse « redirigée » ne peut pas servir une navigation : copie sans cette marque.
async function cleanCopy(response) {
  const body = await response.blob();
  return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
}

// --- Activation : les versions précédentes du site sont supprimées --------------------------------------
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      const oldPages = names.filter((name) => name.startsWith(PAGES_PREFIX) && name !== PAGES);
      const toRefresh = [];
      for (const name of oldPages) {
        const keys = await (await caches.open(name)).keys();
        for (const request of keys) toRefresh.push(new URL(request.url).pathname);
      }
      await Promise.all(
        names
          .filter((name) => (name.startsWith("edulinkage-precache-") && name !== PRECACHE) || oldPages.includes(name))
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
      // Les pages à identifiant gardées appartenaient à l'ancienne version (fichiers supprimés) :
      // retéléchargées pour la nouvelle si internet est là, au mieux (jamais bloquant).
      refreshPages(toRefresh.slice(-40));
    })(),
  );
});

async function refreshPages(paths) {
  const cache = await caches.open(PAGES);
  for (const path of paths) {
    try {
      const response = await fetch(path, { credentials: "same-origin" });
      if (isHtml(response)) await cache.put(path, response.redirected ? await cleanCopy(response) : response);
    } catch {
      return; // hors connexion : inutile d'insister
    }
  }
}

// --- Requêtes --------------------------------------------------------------------------------------------
self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  // API EduLinkage (autre origine) : jamais ici, voir l'en-tête de ce fichier.
  if (url.origin !== self.location.origin) return;
  // Navigation interne de Next.js (données RSC) : réseau seul. Sans réseau, Next.js recharge la
  // page entière, qui est alors servie ci-dessous depuis l'appareil.
  if (request.headers.get("RSC") === "1" || url.searchParams.has("_rsc")) return;

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request, PRECACHE));
  } else if (request.mode === "navigate") {
    event.respondWith(page(request, url.pathname));
  } else if (PRECACHED.has(url.pathname)) {
    event.respondWith(cacheFirst(request, PRECACHE));
  } else if (url.pathname.startsWith("/_next/image") || request.destination === "image") {
    event.respondWith(staleWhileRevalidate(request));
  }
});

async function page(request, path) {
  // Pages sans identifiant : celles de CETTE version du site, gardées à l'installation.
  if (PRECACHED.has(path)) {
    const cached = await caches.match(path, { cacheName: PRECACHE });
    if (cached) return cached;
  }
  try {
    const response = await fetch(request);
    if (!PRECACHED.has(path) && isHtml(response)) {
      const cache = await caches.open(PAGES);
      await cache.put(path, response.redirected ? await cleanCopy(response.clone()) : response.clone());
      void trim(PAGES, MAX_PAGES);
    }
    return response;
  } catch (err) {
    const cached = (await caches.match(path, { cacheName: PAGES })) || (await caches.match(path, { cacheName: PRECACHE }));
    if (cached) return cached;
    const offline = await caches.match(OFFLINE_PAGE, { cacheName: PRECACHE });
    if (offline) return offline;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request, { cacheName });
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(cacheName);
    await cache.put(request, response.clone());
  }
  return response;
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(ASSETS);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(async (response) => {
      if (response.ok) {
        await cache.put(request, response.clone());
        void trim(ASSETS, MAX_ASSETS);
      }
      return response;
    })
    .catch(() => cached || Response.error());
  return cached || network;
}

function isHtml(response) {
  return response.ok && (response.headers.get("Content-Type") || "").includes("text/html");
}

async function trim(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  for (const request of keys.slice(0, Math.max(0, keys.length - max))) await cache.delete(request);
}
