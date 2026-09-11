import { clearStoredTokens, getStoredTokens, setStoredTokens } from "@/lib/auth/session";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

// Phase 27 Sprint 1.1 — distincte de ApiError (qui porte toujours un vrai statut HTTP renvoyé par
// le serveur) : couvre le cas où AUCUNE réponse n'a été reçue (coupure réseau, fetch() qui rejette)
// pendant un refresh. Une session par ailleurs valide ne doit jamais être détruite pour une raison
// transitoire — voir docs/phases/PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md §7/§9, même
// distinction déjà en place côté Mobile (apps/mobile/lib/api/client.ts::NetworkError).
export class NetworkError extends Error {}

export async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    // ignore
  }
  return `Request failed with status ${response.status}`;
}

// Phase 27 Sprint 1.1 — un échec DÉFINITIF de refresh (le serveur rejette explicitement le refresh
// token) doit être connu de AuthProvider pour nettoyer l'état React et déclencher la redirection
// vers /login. Ce module vit hors de l'arbre React et ne peut pas appeler setState directement —
// un registre d'écouteurs minimal fait le pont, même pattern que
// apps/mobile/lib/api/client.ts::onSessionExpired. Volontairement PAS déclenché sur une simple
// coupure réseau pendant le refresh (voir requestRefresh ci-dessous) : la session locale reste
// potentiellement valide.
type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

function notifySessionExpired(): void {
  sessionExpiredListeners.forEach((listener) => listener());
}

async function requestRefresh(): Promise<boolean> {
  const stored = getStoredTokens();
  if (!stored) return false;

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: stored.refresh_token }),
    });
  } catch (err) {
    // Coupure réseau pendant le refresh : ce n'est pas un refus explicite du serveur, la session
    // locale reste potentiellement valide — on ne la détruit jamais pour ça.
    throw new NetworkError(err instanceof Error ? err.message : "Network request failed");
  }
  if (!response.ok) return false;

  const tokens = await response.json();
  setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
  return true;
}

// Phase 27 Sprint 1.1 — "single refresh in flight" : plusieurs requêtes peuvent recevoir 401
// presque simultanément (ex. un tableau de bord qui lance plusieurs GET en parallèle) alors que
// l'access token vient d'expirer. Sans ce verrou, chacune déclenchait son propre appel
// /auth/refresh avec le MÊME refresh_token encore stocké ; côté serveur, ce token est révoqué et
// remplacé dès le premier appel qui aboutit (rotation confirmée par
// apps/api/tests/test_auth.py::test_refresh_rotates_token_and_invalidates_old_one), donc tout
// appel de refresh suivant utilisant l'ancien token recevait 401 à son tour et appelait
// clearStoredTokens(), supprimant les tokens flambant neufs qu'un autre appel venait d'écrire.
// La promesse en cours est mémorisée ; toute requête concurrente attend cette même promesse au
// lieu d'en déclencher une nouvelle, et le verrou est toujours libéré via `finally` — y compris en
// cas d'erreur réseau — pour qu'aucun échec ne le laisse bloqué indéfiniment.
let refreshInFlight: Promise<boolean> | null = null;

function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = requestRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/**
 * Client HTTP partagé par tous les modules authentifiés (école, académique, élèves, notes,
 * bulletins) : attache le token courant et retente une fois après un refresh silencieux sur 401,
 * pour éviter de dupliquer cette logique dans chaque client de module.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () => {
    const stored = getStoredTokens();
    const headers = new Headers(init.headers);
    if (stored) headers.set("Authorization", `Bearer ${stored.access_token}`);
    return fetch(`${API_URL}${path}`, { ...init, headers });
  };

  let response = await doFetch();

  if (response.status === 401) {
    // Une NetworkError ici remonte telle quelle (voir requestRefresh) : une session par ailleurs
    // valide n'est jamais détruite pour une coupure réseau transitoire.
    const refreshed = await refreshTokens();
    if (refreshed) {
      response = await doFetch();
    } else {
      // Le serveur a explicitement rejeté le refresh (401/403/token invalide) : session terminée.
      clearStoredTokens();
      notifySessionExpired();
    }
  }

  if (!response.ok) {
    // Phase 27 Sprint 1.1 — un 401 atteignant ce point ne peut provenir que d'un appel passé par
    // apiFetch (toujours une requête déjà authentifiée), jamais de /auth/login (qui utilise fetch()
    // directement dans lib/auth/client.ts et garde son propre message "Invalid email or password").
    // Il signifie donc toujours "cette session n'est plus valable", jamais une erreur applicative —
    // message générique plutôt que le texte technique brut du backend ("Could not validate
    // credentials"), voir Discovery §11/§14.
    if (response.status === 401) {
      throw new ApiError("Votre session a expiré. Veuillez vous reconnecter.", 401);
    }
    throw new ApiError(await parseErrorDetail(response), response.status);
  }
  return response;
}
