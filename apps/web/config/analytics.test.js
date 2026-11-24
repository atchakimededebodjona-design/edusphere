// Mesure d'audience Umami (2026-11-24) — `node --test config/analytics.test.js`.
const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveAnalytics } = require("./analytics");

const ID = "94db1cb1-74f4-4a40-ad6c-962362670409";

test("aucune variable : aucune mesure", () => {
  assert.equal(resolveAnalytics({}), null);
  assert.equal(resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: " ", NEXT_PUBLIC_UMAMI_WEBSITE_ID: "" }), null);
});

test("une seule des deux variables : refus", () => {
  assert.throws(() => resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: "https://stats.example.com/script.js" }));
  assert.throws(() => resolveAnalytics({ NEXT_PUBLIC_UMAMI_WEBSITE_ID: ID }));
});

test("configuration valide : origine extraite pour la CSP", () => {
  const result = resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: "https://stats.example.com/script.js", NEXT_PUBLIC_UMAMI_WEBSITE_ID: ID.toUpperCase() });
  assert.deepEqual(result, { src: "https://stats.example.com/script.js", websiteId: ID, origin: "https://stats.example.com" });
});

test("http refusé hors serveur local, identifiants, requête ou fragment refusés", () => {
  for (const src of [
    "http://stats.example.com/script.js",
    "https://user:pw@stats.example.com/script.js",
    "https://stats.example.com/script.js?x=1",
    "https://stats.example.com/script.js#x",
    "pas une adresse",
  ]) {
    assert.throws(() => resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: src, NEXT_PUBLIC_UMAMI_WEBSITE_ID: ID }), src);
  }
  assert.equal(resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: "http://127.0.0.1:3999/script.js", NEXT_PUBLIC_UMAMI_WEBSITE_ID: ID }).origin, "http://127.0.0.1:3999");
});

test("identifiant du site : UUID obligatoire", () => {
  assert.throws(() => resolveAnalytics({ NEXT_PUBLIC_UMAMI_SRC: "https://stats.example.com/script.js", NEXT_PUBLIC_UMAMI_WEBSITE_ID: "G-12345" }));
});
