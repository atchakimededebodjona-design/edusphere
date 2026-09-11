"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, onSessionExpired } from "@/lib/api/client";
import * as authClient from "@/lib/auth/client";
import type { Me } from "@/lib/auth/client";
import { getStoredTokens, setStoredTokens } from "@/lib/auth/session";
import { listSchools, type School } from "@/lib/schools/client";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

// Phase 8.1 — un admin créé par /register n'a qu'un rôle scopé ORGANISATION (school_id null,
// voir auth/service.py::register) : il n'a pas de "current school" évident. On le résout ici en
// interrogeant les écoles de son organisation (GET /schools?organization_id=..., déjà existant
// et déjà isolé par tenant — voir tests/test_tenant_isolation.py). Un rôle scopé école (compte
// créé via la page Utilisateurs) reste prioritaire et inchangé.
export type SchoolContextStatus = "loading" | "resolved" | "selection-needed" | "empty" | "error";

const SELECTED_SCHOOL_STORAGE_KEY = "edulinkage.selected_school_id";
// Phase 27 Sprint 1.1 — ancienne clé, avant la normalisation de marque (voir
// docs/phases/PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md §2/§6). Cette valeur n'a jamais été
// une preuve d'autorisation (voir `stillValid` ci-dessous, qui revalide toujours contre la liste
// réelle des écoles renvoyée par l'API) — la migrer d'une clé de stockage à une autre ne change
// rien aux contrôles serveur.
const LEGACY_SELECTED_SCHOOL_STORAGE_KEY = "edusphere.selected_school_id";

function readSelectedSchoolId(): string | null {
  const current = window.localStorage.getItem(SELECTED_SCHOOL_STORAGE_KEY);
  if (current) return current;

  const legacy = window.localStorage.getItem(LEGACY_SELECTED_SCHOOL_STORAGE_KEY);
  if (legacy) {
    window.localStorage.setItem(SELECTED_SCHOOL_STORAGE_KEY, legacy);
    window.localStorage.removeItem(LEGACY_SELECTED_SCHOOL_STORAGE_KEY);
  }
  return legacy;
}

export type AuthContextValue = {
  status: AuthStatus;
  user: Me["user"] | null;
  roles: Me["roles"];
  permissions: string[];
  currentSchoolId: string | null;
  schoolContextStatus: SchoolContextStatus;
  availableSchools: School[];
  schoolContextError: string | null;
  selectSchool: (schoolId: string) => void;
  retrySchoolContext: () => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

function formatSchoolContextError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "Votre session a expiré. Reconnectez-vous pour continuer.";
    if (err.status >= 500) return "Une erreur serveur est survenue. Réessayez.";
    return err.message || "Impossible de déterminer votre école.";
  }
  return "Erreur réseau : vérifiez votre connexion et réessayez.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const [schoolContextStatus, setSchoolContextStatus] = useState<SchoolContextStatus>("loading");
  const [availableSchools, setAvailableSchools] = useState<School[]>([]);
  const [schoolContextError, setSchoolContextError] = useState<string | null>(null);
  const [selectedSchoolId, setSelectedSchoolId] = useState<string | null>(null);
  const [resolveAttempt, setResolveAttempt] = useState(0);

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
    if (getStoredTokens()) {
      void loadMe();
    } else {
      setStatus("anonymous");
    }
  }, [loadMe]);

  // Phase 27 Sprint 1.1 — un 401 rencontré n'importe où dans l'app (pas seulement au chargement
  // initial) peut révéler un refresh token expiré/révoqué. `apiFetch` vit hors de l'arbre React et
  // ne peut pas modifier cet état directement ; il notifie via `onSessionExpired`, et c'est ici
  // qu'on repasse réellement en "anonymous" — ce qui fait déclencher la redirection déjà existante
  // dans AuthGate, sans aucun code de navigation supplémentaire (même pattern que
  // apps/mobile/lib/auth/AuthProvider.tsx, voir Discovery §7/§15).
  useEffect(() => {
    return onSessionExpired(() => {
      setMe(null);
      setStatus("anonymous");
      setSchoolContextStatus("loading");
      setAvailableSchools([]);
      setSchoolContextError(null);
      setSelectedSchoolId(null);
    });
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authClient.login(email, password);
      setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    await authClient.logout();
    setMe(null);
    setStatus("anonymous");
    setSchoolContextStatus("loading");
    setAvailableSchools([]);
    setSchoolContextError(null);
    setSelectedSchoolId(null);
  }, []);

  const schoolScopedRoleId = useMemo(() => me?.roles.find((role) => role.school_id)?.school_id ?? null, [me]);
  // Un seul rôle scopé organisation est réellement produit aujourd'hui (register()) — pas de
  // support de plusieurs organisations simultanées, ce cas n'existe pas dans le produit actuel.
  const orgScopedRole = useMemo(
    () => me?.roles.find((role) => !role.school_id && role.organization_id) ?? null,
    [me],
  );

  useEffect(() => {
    if (status !== "authenticated" || !me) return;

    if (schoolScopedRoleId) {
      setSchoolContextStatus("resolved");
      return;
    }

    if (!orgScopedRole?.organization_id) {
      // Ni rôle scopé école, ni rôle scopé organisation (ex. rôle plateforme SUPER_ADMIN /
      // PLATFORM_SUPPORT, organization_id ET school_id nuls) : aucune "école courante" n'a de
      // sens pour ce compte avec les écrans actuels.
      setSchoolContextStatus("empty");
      return;
    }

    let cancelled = false;
    setSchoolContextStatus("loading");
    setSchoolContextError(null);

    listSchools(orgScopedRole.organization_id)
      .then((schools) => {
        if (cancelled) return;
        setAvailableSchools(schools);
        if (schools.length === 0) {
          setSchoolContextStatus("empty");
        } else if (schools.length === 1) {
          setSelectedSchoolId(schools[0].id);
          setSchoolContextStatus("resolved");
        } else {
          // Plusieurs écoles pour cette organisation : jamais de sélection arbitraire. On
          // réutilise un choix déjà fait explicitement sur ce navigateur s'il est toujours
          // valide, sinon on demande une sélection explicite (AuthGate).
          const remembered = readSelectedSchoolId();
          const stillValid = remembered && schools.some((s) => s.id === remembered);
          if (stillValid) {
            setSelectedSchoolId(remembered);
            setSchoolContextStatus("resolved");
          } else {
            setSchoolContextStatus("selection-needed");
          }
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setSchoolContextError(formatSchoolContextError(err));
        setSchoolContextStatus("error");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, me, schoolScopedRoleId, orgScopedRole, resolveAttempt]);

  const selectSchool = useCallback((schoolId: string) => {
    window.localStorage.setItem(SELECTED_SCHOOL_STORAGE_KEY, schoolId);
    setSelectedSchoolId(schoolId);
    setSchoolContextStatus("resolved");
  }, []);

  const retrySchoolContext = useCallback(() => {
    setResolveAttempt((n) => n + 1);
  }, []);

  const currentSchoolId = useMemo(() => schoolScopedRoleId ?? selectedSchoolId, [schoolScopedRoleId, selectedSchoolId]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: me?.user ?? null,
      roles: me?.roles ?? [],
      permissions: me?.permissions ?? [],
      currentSchoolId,
      schoolContextStatus,
      availableSchools,
      schoolContextError,
      selectSchool,
      retrySchoolContext,
      login,
      logout,
    }),
    [
      status,
      me,
      currentSchoolId,
      schoolContextStatus,
      availableSchools,
      schoolContextError,
      selectSchool,
      retrySchoolContext,
      login,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
