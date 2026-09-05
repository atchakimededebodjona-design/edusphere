import { clearStoredTokens, getStoredTokens, setStoredTokens } from "@/lib/auth/session";

// http://localhost:8000 fonctionne pour iOS simulator ; l'émulateur Android nécessite
// 10.0.2.2, un appareil physique l'IP LAN de la machine de dev — à ajuster via .env local
// (voir .env.example), pas de valeur unique qui marche partout.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

// Phase 12 — distincts de ApiError (qui porte toujours un vrai status HTTP renvoyé par le
// serveur) : ces deux classes couvrent les cas où AUCUNE réponse n'a été reçue — coupure réseau
// (fetch rejette) et dépassement du délai (abort volontaire ci-dessous, voir fetchWithTimeout).
// La distinction permet à toUserMessage() de donner le message le plus juste sans jamais exposer
// l'erreur technique brute ("Network request failed", nom de domaine, etc. — cf. règle UX §7).
export class NetworkError extends Error {}
export class TimeoutError extends Error {}

// 15s : généreux pour un réseau mobile 3G/4G instable, mais fini — aucune requête ne doit
// laisser un écran en Loading indéfiniment (Phase 12, problème actif identifié en Discovery).
const DEFAULT_TIMEOUT_MS = 15000;

export async function fetchWithTimeout(
  input: string,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw new TimeoutError();
    throw new NetworkError(err instanceof Error ? err.message : "Network request failed");
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Message utilisateur centralisé (Phase 12) — un seul endroit à maintenir pour respecter la
 * règle "jamais de stack trace, token ou URL interne affiché". Les écrans n'ont plus besoin de
 * réimplémenter chacun leur propre `instanceof ApiError ? ... : "..."`.
 */
export function toUserMessage(err: unknown): string {
  if (err instanceof TimeoutError) {
    return "Le chargement a pris trop de temps. Vérifiez votre connexion puis réessayez.";
  }
  if (err instanceof NetworkError) {
    return "Impossible de contacter le serveur. Vérifiez votre connexion puis réessayez.";
  }
  if (err instanceof ApiError) return err.message;
  return "Une erreur est survenue. Réessayez.";
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    // ignore
  }
  return `Request failed with status ${response.status}`;
}

// Phase 12 — un échec DÉFINITIF de refresh (le serveur rejette explicitement le refresh token :
// expiré/révoqué) doit être connu de l'AuthProvider pour renvoyer l'utilisateur vers /login. Ce
// module utilitaire vit hors de l'arbre React et ne peut pas appeler un setState directement —
// un registre d'écouteurs minimal fait le pont, sans nouvelle dépendance de state management.
// Volontairement PAS déclenché en cas de simple coupure réseau/timeout pendant le refresh (voir
// apiFetch ci-dessous) : une session valide ne doit pas être détruite pour une raison transitoire.
type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

function notifySessionExpired(): void {
  sessionExpiredListeners.forEach((listener) => listener());
}

// Exporté (uniquement) pour les téléchargements de fichiers binaires (ex. PDF de bulletin, cf.
// lib/parent/client.ts) : ceux-ci passent par expo-file-system::downloadAsync plutôt que par
// `fetch` (transfert binaire natif, pas de conversion Blob/base64 côté JS), donc en dehors du
// flux normal de `apiFetch` — mais doivent réutiliser exactement la même logique de
// rafraîchissement de token en cas de 401, pas une copie divergente.
export async function refreshTokens(): Promise<boolean> {
  const stored = await getStoredTokens();
  if (!stored) return false;

  const response = await fetchWithTimeout(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: stored.refresh_token }),
  });
  if (!response.ok) return false;

  const tokens = await response.json();
  await setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
  return true;
}

/**
 * Client HTTP partagé par tous les modules — même contrat que apps/web/lib/api/client.ts,
 * porté à expo-secure-store au lieu de localStorage (voir lib/auth/session.ts).
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = async () => {
    const stored = await getStoredTokens();
    const headers = new Headers(init.headers);
    if (stored) headers.set("Authorization", `Bearer ${stored.access_token}`);
    return fetchWithTimeout(`${API_URL}${path}`, { ...init, headers });
  };

  let response = await doFetch();

  if (response.status === 401) {
    let refreshed: boolean;
    try {
      refreshed = await refreshTokens();
    } catch (err) {
      // Coupure réseau/timeout PENDANT le refresh : ce n'est pas un refus explicite du serveur,
      // la session locale reste potentiellement valide. On ne la détruit pas — on remonte
      // l'erreur réseau telle quelle pour que l'écran affiche "Réessayer" sans déconnecter
      // l'utilisateur à tort (voir §6 de la Phase 12 : ne pas confondre "injoignable" et
      // "définitivement invalide").
      throw err;
    }

    if (refreshed) {
      response = await doFetch();
    } else {
      // Le serveur a explicitement rejeté le refresh token : session réellement terminée.
      await clearStoredTokens();
      notifySessionExpired();
    }
  }

  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response;
}
