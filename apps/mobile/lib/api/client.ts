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

async function refreshTokens(): Promise<boolean> {
  const stored = await getStoredTokens();
  if (!stored) return false;

  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
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
    return fetch(`${API_URL}${path}`, { ...init, headers });
  };

  let response = await doFetch();

  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      response = await doFetch();
    } else {
      await clearStoredTokens();
    }
  }

  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response;
}
