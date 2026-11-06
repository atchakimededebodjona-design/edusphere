// Tests de configuration (risque H1) — `node --test config/` (runner intégré à Node, aucune
// dépendance ajoutée). Couvre le validateur ET la configuration Next réelle (next.config.js),
// chargée exactement comme `next build` / `next dev` / `next lint` la chargent (fonction de phase).
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { validateProductionApiUrl, resolveApiUrl, NON_DEPLOYABLE_FLAG } = require("./apiUrl");

// Placeholder volontaire (domaine réservé à la documentation, RFC 2606) : jamais le vrai domaine.
const VALID_HTTPS = "https://api.example.com";

test("production : variable absente, vide ou blanche => refus", () => {
  for (const raw of [undefined, "", "   "]) {
    assert.equal(validateProductionApiUrl(raw).ok, false, String(raw));
  }
});

test("production : URL mal formée, protocole non http(s), identifiants, query, barre finale => refus", () => {
  for (const raw of ["api.example.com", "not a url", "ftp://api.example.com", "https://user:pw@api.example.com",
    "https://api.example.com?x=1", "https://api.example.com#x", "https://api.example.com/"]) {
    assert.equal(validateProductionApiUrl(raw).ok, false, raw);
  }
});

test("production : adresses locales => refus", () => {
  for (const raw of ["http://localhost:8000", "http://127.0.0.1:8000", "https://localhost", "http://127.1.2.3",
    "http://0.0.0.0:8000", "http://[::1]:8000", "http://app.localhost", "HTTP://LOCALHOST:8000"]) {
    const result = validateProductionApiUrl(raw);
    assert.equal(result.ok, false, raw);
  }
});

test("production : URL HTTPS distante valide => acceptée sans avertissement", () => {
  const result = validateProductionApiUrl(VALID_HTTPS);
  assert.deepEqual(result, { ok: true, url: VALID_HTTPS, warnings: [] });
  assert.equal(validateProductionApiUrl("https://example.com/backend").ok, true);
});

test("production : http distant accepté avec avertissement (HTTPS de production pas encore en place)", () => {
  const result = validateProductionApiUrl("http://api.example.com");
  assert.equal(result.ok, true);
  assert.equal(result.warnings.length, 1);
});

test("resolveApiUrl : strict => exception explicite ; non strict (dev/start/lint) => repli local", () => {
  assert.throws(() => resolveApiUrl({ env: {}, strict: true }), /Build de production refusé/);
  assert.throws(() => resolveApiUrl({ env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" }, strict: true }), /adresse locale/);
  assert.deepEqual(resolveApiUrl({ env: {}, strict: false }), { url: "http://localhost:8000", warnings: [] });
  assert.equal(resolveApiUrl({ env: { NEXT_PUBLIC_API_URL: VALID_HTTPS }, strict: true }).url, VALID_HTTPS);
});

test("resolveApiUrl : drapeau non déployable explicite => repli local autorisé, avec avertissement", () => {
  const result = resolveApiUrl({ env: { [NON_DEPLOYABLE_FLAG]: "1" }, strict: true });
  assert.equal(result.url, "http://localhost:8000");
  assert.match(result.warnings[0], /NON DÉPLOYABLE/);
  assert.equal(resolveApiUrl({ env: { [NON_DEPLOYABLE_FLAG]: "0" }, strict: false }).url, "http://localhost:8000");
  assert.throws(() => resolveApiUrl({ env: { [NON_DEPLOYABLE_FLAG]: "0" }, strict: true }));
});

// --- next.config.js réel (phases Next) ------------------------------------------------------------
function loadNextConfig(phase, env, argv = ["node", "next", "build"]) {
  const configPath = path.join(__dirname, "..", "next.config.js");
  const saved = { env: process.env, argv: process.argv, warn: console.warn };
  process.env = { ...env };
  process.argv = argv;
  console.warn = () => {};
  try {
    delete require.cache[require.resolve(configPath)];
    return require(configPath)(phase);
  } finally {
    process.env = saved.env;
    process.argv = saved.argv;
    console.warn = saved.warn;
  }
}

test("next.config.js : `next build` refusé sans URL valide, accepté avec une URL HTTPS distante", () => {
  const { PHASE_PRODUCTION_BUILD } = require("next/constants");
  for (const value of [undefined, "", "http://localhost:8000", "http://127.0.0.1:8000", "not-a-url"]) {
    const env = value === undefined ? {} : { NEXT_PUBLIC_API_URL: value };
    assert.throws(() => loadNextConfig(PHASE_PRODUCTION_BUILD, env), /Build de production refusé/, String(value));
  }
  const config = loadNextConfig(PHASE_PRODUCTION_BUILD, { NEXT_PUBLIC_API_URL: VALID_HTTPS });
  assert.equal(config.env.NEXT_PUBLIC_API_URL, VALID_HTTPS);
});

test("next.config.js : dev, start et lint inchangés (repli local, jamais d'échec)", () => {
  const { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_SERVER, PHASE_PRODUCTION_BUILD } = require("next/constants");
  assert.equal(loadNextConfig(PHASE_DEVELOPMENT_SERVER, {}).env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
  assert.equal(loadNextConfig(PHASE_PRODUCTION_SERVER, {}).env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
  const lint = loadNextConfig(PHASE_PRODUCTION_BUILD, {}, ["node", "next", "lint"]);
  assert.equal(lint.env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
  const ci = loadNextConfig(PHASE_PRODUCTION_BUILD, { [NON_DEPLOYABLE_FLAG]: "1" });
  assert.equal(ci.env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
});
