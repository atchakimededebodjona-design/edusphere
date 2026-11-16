const STORAGE_KEY = "edulinkage.session";
// Phase 27 Sprint 1.1 — ancienne clé, avant la normalisation de marque (voir
// docs/phases/PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md). Lue en repli UNIQUEMENT pour migrer
// une session déjà légitimement émise par le serveur vers la nouvelle clé de stockage — jamais
// traitée comme une preuve d'authentification en soi : ce sont toujours les validations JWT/
// refresh existantes (apiFetch, GET /auth/me) qui décident si une session est réellement valide.
const LEGACY_STORAGE_KEY = "edusphere.session";

export type StoredTokens = {
  access_token: string;
  refresh_token: string;
};

function isStoredTokens(value: unknown): value is StoredTokens {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as StoredTokens).access_token === "string" &&
    typeof (value as StoredTokens).refresh_token === "string"
  );
}

function readTokens(key: string): StoredTokens | null {
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return isStoredTokens(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function getStoredTokens(): StoredTokens | null {
  if (typeof window === "undefined") return null;

  const current = readTokens(STORAGE_KEY);
  if (current) return current;

  // Migration douce : une session encore valide sous l'ancienne clé ne doit jamais devenir
  // invisible simplement parce que la clé de stockage a changé de nom (voir le scénario
  // "Could not validate credentials" documenté dans la Discovery). Une valeur absente ou
  // malformée sous l'ancienne clé est traitée exactement comme "pas de session", sans jamais
  // lever d'exception globale ni contourner une quelconque validation.
  const legacy = readTokens(LEGACY_STORAGE_KEY);
  if (legacy) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    return legacy;
  }

  return null;
}

/**
 * Identifiant du compte connecté, lu dans le jeton d'accès (`sub`), SANS vérification de
 * signature. Sert uniquement à ranger par compte les données gardées pour le hors connexion (voir
 * lib/offline/responseCache.ts) — jamais une preuve d'identité : l'API reste seule juge.
 */
export function getStoredUserId(): string | null {
  const tokens = getStoredTokens();
  if (!tokens) return null;
  try {
    const payload = tokens.access_token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const sub = (JSON.parse(window.atob(base64)) as { sub?: unknown }).sub;
    return typeof sub === "string" && sub ? sub : null;
  } catch {
    return null;
  }
}

export function setStoredTokens(tokens: StoredTokens): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

export function clearStoredTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
}
