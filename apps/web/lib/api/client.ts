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

async function refreshTokens(): Promise<boolean> {
  const stored = getStoredTokens();
  if (!stored) return false;

  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: stored.refresh_token }),
  });
  if (!response.ok) return false;

  const tokens = await response.json();
  setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
  return true;
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
    const refreshed = await refreshTokens();
    if (refreshed) {
      response = await doFetch();
    } else {
      clearStoredTokens();
    }
  }

  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response;
}
