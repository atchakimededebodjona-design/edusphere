import assert from "node:assert/strict";
import { test } from "node:test";
import { buildPrecacheList, renderServiceWorker } from "./generate-sw.mjs";

test("garde les pages statiques, le code et les fichiers publics, sans la 404 interne, sw.js ni fichiers cachés", () => {
  const list = buildPrecacheList({
    routes: ["/teacher", "/", "/_not-found", "/offline", "/teacher", "/attendance.rsc"],
    staticFiles: ["chunks/main-abc.js", "css/app.css"],
    publicFiles: ["sw.js", ".gitkeep", "icons/.DS_Store", "icons/icon-192.png", "branding/edulinkage-symbol.png"],
  });
  assert.deepEqual(list, [
    "/",
    "/_next/static/chunks/main-abc.js",
    "/_next/static/css/app.css",
    "/branding/edulinkage-symbol.png",
    "/icons/icon-192.png",
    "/offline",
    "/teacher",
  ]);
});

test("convertit les séparateurs Windows en chemins d'URL", () => {
  const list = buildPrecacheList({
    routes: [],
    staticFiles: ["chunks\\app\\page-1.js"],
    publicFiles: ["icons\\icon-512.png"],
  });
  assert.deepEqual(list, ["/_next/static/chunks/app/page-1.js", "/icons/icon-512.png"]);
});

test("le fichier produit déclare la version et la liste avant le modèle", () => {
  const out = renderServiceWorker({ version: "abc_DEF-1", precache: ["/", "/offline"], template: "// modèle" });
  assert.match(out, /self\.__EDULINKAGE_SW__ = \{"version":"abc_DEF-1","precache":\["\/","\/offline"\]\};/);
  assert.ok(out.endsWith("// modèle"));
});

test("refuse un identifiant de build inattendu", () => {
  assert.throws(() => renderServiceWorker({ version: 'x"; alert(1)', precache: [], template: "" }));
});
