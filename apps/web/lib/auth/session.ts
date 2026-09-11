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

export function setStoredTokens(tokens: StoredTokens): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

export function clearStoredTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
}
