import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import * as authClient from "@/lib/auth/client";
import type { Me } from "@/lib/auth/client";
import { onSessionExpired } from "@/lib/api/client";
import { getStoredTokens, setStoredTokens } from "@/lib/auth/session";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export type AuthContextValue = {
  status: AuthStatus;
  user: Me["user"] | null;
  roles: Me["roles"];
  permissions: string[];
  currentSchoolId: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const loadMe = useCallback(async () => {
    try {
      const result = await authClient.me();
      setMe(result);
      setStatus("authenticated");
    } catch {
      setMe(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const stored = await getStoredTokens();
      if (stored) {
        await loadMe();
      } else {
        setStatus("anonymous");
      }
    })();
  }, [loadMe]);

  // Phase 12 — un 401 rencontré n'importe où dans l'app (pas seulement au chargement initial)
  // peut révéler un refresh token expiré/révoqué. `apiFetch` vit hors de l'arbre React et ne peut
  // pas modifier cet état directement ; il notifie via `onSessionExpired`, et c'est ici qu'on
  // repasse réellement en "anonymous" — ce qui fait automatiquement rediriger vers /login via les
  // `Redirect` déjà présents dans (teacher)/_layout.tsx et (parent)/_layout.tsx, sans aucun code
  // de navigation supplémentaire à écrire.
  useEffect(() => {
    return onSessionExpired(() => {
      setMe(null);
      setStatus("anonymous");
    });
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authClient.login(email, password);
      await setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    await authClient.logout();
    setMe(null);
    setStatus("anonymous");
  }, []);

  const currentSchoolId = useMemo(() => me?.roles.find((role) => role.school_id)?.school_id ?? null, [me]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: me?.user ?? null,
      roles: me?.roles ?? [],
      permissions: me?.permissions ?? [],
      currentSchoolId,
      login,
      logout,
    }),
    [status, me, currentSchoolId, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
