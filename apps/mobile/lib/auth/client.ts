import { API_URL, ApiError, apiFetch } from "@/lib/api/client";
import { clearStoredTokens, getStoredTokens } from "@/lib/auth/session";

export { ApiError };

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
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

export async function login(email: string, password: string): Promise<TokenPair> {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new ApiError(await parseErrorDetail(response), response.status);
  return response.json();
}

export async function logout(): Promise<void> {
  const stored = await getStoredTokens();
  if (stored) {
    try {
      await fetch(`${API_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored.refresh_token }),
      });
    } catch {
      // best-effort — la session locale est effacée même si la révocation échoue
    }
  }
  await clearStoredTokens();
}

export async function me(): Promise<Me> {
  const response = await apiFetch("/api/v1/auth/me");
  return response.json();
}
