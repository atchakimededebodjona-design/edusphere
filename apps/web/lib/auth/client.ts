import { API_URL, ApiError, apiFetch, parseErrorDetail } from "@/lib/api/client";
import { clearStoredTokens, getStoredTokens } from "@/lib/auth/session";

export { ApiError };

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type RegisterPayload = {
  organization_name: string;
  organization_slug: string;
  country_code: string;
  school_name: string;
  school_slug: string;
  admin_full_name: string;
  admin_email: string;
  admin_password: string;
};

export type RoleAssignment = {
  role_code: string;
  organization_id: string | null;
  school_id: string | null;
};

export type Me = {
  user: {
    id: string;
    email: string;
    full_name: string;
    phone: string | null;
    is_active: boolean;
    is_platform_admin: boolean;
  };
  roles: RoleAssignment[];
  permissions: string[];
};

export async function login(email: string, password: string): Promise<TokenPair> {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response.json();
}

export async function register(payload: RegisterPayload): Promise<{ tokens: TokenPair }> {
  const response = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response.json();
}

export async function refresh(refreshToken: string): Promise<TokenPair> {
  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response.json();
}

export async function logout(): Promise<void> {
  const stored = getStoredTokens();
  if (stored) {
    // Best-effort : la session locale est effacée même si l'appel de révocation échoue
    // (réseau coupé, refresh token déjà expiré, etc.).
    try {
      await fetch(`${API_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored.refresh_token }),
      });
    } catch {
      // ignore
    }
  }
  clearStoredTokens();
}

export async function me(): Promise<Me> {
  const response = await apiFetch("/api/v1/auth/me");
  return response.json();
}
