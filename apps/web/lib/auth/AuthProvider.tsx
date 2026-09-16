"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, onSessionExpired } from "@/lib/api/client";
import * as authClient from "@/lib/auth/client";
import type { Me } from "@/lib/auth/client";
import { getStoredTokens, setStoredTokens } from "@/lib/auth/session";
import {
  distinctOrganizationIds,
  organizationIdForSchool,
  readLegacySchoolId,
  readStoredTenantContext,
  resolveSchoolScopedFastPath,
  schoolScopedIdsForOrganization,
  writeTenantContext,
} from "@/lib/auth/tenantContext";
import { getOrganization, type Organization } from "@/lib/organizations/client";
import { getSchool, listSchools, type School } from "@/lib/schools/client";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

// Contexte tenant à deux niveaux (organisation -> école) — voir docs/mission "sélection
// multi-organisation/multi-école". Un compte peut avoir accès à plusieurs organisations, et
// plusieurs écoles au sein de chacune ; aucune des deux n'est jamais choisie arbitrairement
// (jamais le premier rôle du tableau `roles`, jamais un ordre implicite) — voir
// lib/auth/tenantContext.ts pour la logique de résolution pure.
export type TenantContextStatus = "loading" | "resolved" | "selection-needed" | "empty" | "error";

export type AuthContextValue = {
  status: AuthStatus;
  user: Me["user"] | null;
  roles: Me["roles"];
  permissions: string[];

  currentOrganizationId: string | null;
  currentOrganization: Organization | null;
  organizationContextStatus: TenantContextStatus;
  availableOrganizations: Organization[];
  organizationContextError: string | null;
  selectOrganization: (organizationId: string) => void;

  currentSchoolId: string | null;
  currentSchool: School | null;
  schoolContextStatus: TenantContextStatus;
  availableSchools: School[];
  schoolContextError: string | null;
  selectSchool: (schoolId: string) => void;

  retryTenantContext: () => void;

  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

// Un contexte mémorisé {organizationId, schoolId} ne doit jamais être utilisé partiellement : si
// l'organisation est accessible mais que l'école mémorisée ne lui appartient pas (ex. reliquat
// d'un état antérieur incohérent, ou école déplacée/supprimée), le contexte entier est traité
// comme invalide — jamais un simple recours à un nouvel écran d'école pour la même organisation
// choisie implicitement.
async function isSchoolAccessibleInOrganization(
  organizationId: string,
  schoolId: string,
  roles: Me["roles"],
): Promise<boolean> {
  const roleSchoolIds = schoolScopedIdsForOrganization(roles, organizationId);
  if (roleSchoolIds.length > 0) return roleSchoolIds.includes(schoolId);
  try {
    const schools = await listSchools(organizationId);
    return schools.some((s) => s.id === schoolId);
  } catch {
    return false;
  }
}

function formatTenantContextError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "Votre session a expiré. Reconnectez-vous pour continuer.";
    if (err.status >= 500) return "Une erreur serveur est survenue. Réessayez.";
    return err.message || "Impossible de déterminer votre contexte de travail.";
  }
  return "Erreur réseau : vérifiez votre connexion et réessayez.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const [currentOrganizationId, setCurrentOrganizationId] = useState<string | null>(null);
  // Objet complet (nom inclus) de l'organisation courante — jamais dérivable des `roles` seuls
  // (qui ne portent qu'un `organization_id`) : nécessaire pour ne jamais afficher un UUID/slug à
  // l'utilisateur (sélecteur de contexte, voir components/app-shell/TenantSwitcher.tsx).
  const [currentOrganization, setCurrentOrganization] = useState<Organization | null>(null);
  const [organizationContextStatus, setOrganizationContextStatus] = useState<TenantContextStatus>("loading");
  const [availableOrganizations, setAvailableOrganizations] = useState<Organization[]>([]);
  const [organizationContextError, setOrganizationContextError] = useState<string | null>(null);

  const [currentSchoolId, setCurrentSchoolId] = useState<string | null>(null);
  const [currentSchool, setCurrentSchool] = useState<School | null>(null);
  const [schoolContextStatus, setSchoolContextStatus] = useState<TenantContextStatus>("loading");
  const [availableSchools, setAvailableSchools] = useState<School[]>([]);
  const [schoolContextError, setSchoolContextError] = useState<string | null>(null);

  const [resolveAttempt, setResolveAttempt] = useState(0);

  const resetTenantState = useCallback(() => {
    setCurrentOrganizationId(null);
    setCurrentOrganization(null);
    setOrganizationContextStatus("loading");
    setAvailableOrganizations([]);
    setOrganizationContextError(null);
    setCurrentSchoolId(null);
    setCurrentSchool(null);
    setSchoolContextStatus("loading");
    setAvailableSchools([]);
    setSchoolContextError(null);
  }, []);

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

  // Phase 27 Sprint 1.1 — un 401 rencontré n'importe où dans l'app peut révéler un refresh token
  // expiré/révoqué ; `apiFetch` notifie via `onSessionExpired` (voir api/client.ts), et c'est ici
  // qu'on repasse réellement en "anonymous" (déclenche la redirection déjà existante dans
  // AuthGate, sans code de navigation supplémentaire).
  useEffect(() => {
    return onSessionExpired(() => {
      setMe(null);
      setStatus("anonymous");
      resetTenantState();
    });
  }, [resetTenantState]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authClient.login(email, password);
      setStoredTokens({ access_token: tokens.access_token, refresh_token: tokens.refresh_token });
      await loadMe();
    },
    [loadMe],
  );

  // Contexte tenant nettoyé (état React remis à zéro) sur déconnexion — mais le choix mémorisé en
  // localStorage n'est jamais effacé ici : une reconnexion ultérieure du même compte sur ce même
  // navigateur doit pouvoir le restaurer (revalidé contre l'API, jamais fait confiance tel quel —
  // voir resolveSchoolsForOrganization ci-dessous).
  const logout = useCallback(async () => {
    await authClient.logout();
    setMe(null);
    setStatus("anonymous");
    resetTenantState();
  }, [resetTenantState]);

  // Résout les écoles d'UNE organisation déjà déterminée (auto ou choisie explicitement) :
  // - `GET /schools?organization_id=...` (existant) fonctionne pour un rôle org-wide
  //   (SCHOOL_ADMIN/DIRECTOR-style, school_id NULL) ;
  // - un rôle scopé à des écoles précises (ex. enseignant) n'a PAS `schools.read` au niveau
  //   organisation (voir apps/api/app/core/permissions.py::get_scoped_permission_codes — un rôle
  //   school_id non-null ne compte jamais pour un contrôle organization_id seul) : en cas
  //   d'échec, on reconstitue la liste directement depuis les écoles auxquelles ce compte a
  //   réellement un rôle (`GET /schools/{id}`, autorisé école par école).
  const resolveSchoolsForOrganization = useCallback(
    async (organizationId: string, roles: Me["roles"], cancelledRef: { current: boolean }) => {
      setSchoolContextStatus("loading");
      setSchoolContextError(null);

      const roleSchoolIds = schoolScopedIdsForOrganization(roles, organizationId);
      let schools: School[];
      try {
        schools = await listSchools(organizationId);
      } catch (err) {
        if (roleSchoolIds.length === 0) {
          if (cancelledRef.current) return;
          setSchoolContextError(formatTenantContextError(err));
          setSchoolContextStatus("error");
          return;
        }
        try {
          schools = await Promise.all(roleSchoolIds.map((id) => getSchool(id)));
        } catch (fallbackErr) {
          if (cancelledRef.current) return;
          setSchoolContextError(formatTenantContextError(fallbackErr));
          setSchoolContextStatus("error");
          return;
        }
      }
      if (cancelledRef.current) return;

      const scoped = roleSchoolIds.length > 0 ? schools.filter((s) => roleSchoolIds.includes(s.id)) : schools;
      setAvailableSchools(scoped);

      if (scoped.length === 0) {
        setCurrentSchool(null);
        setSchoolContextStatus("empty");
        return;
      }
      if (scoped.length === 1) {
        setCurrentSchoolId(scoped[0].id);
        setCurrentSchool(scoped[0]);
        setSchoolContextStatus("resolved");
        writeTenantContext({ organizationId, schoolId: scoped[0].id });
        return;
      }

      // Plusieurs écoles pour cette organisation : jamais de sélection arbitraire. Un choix déjà
      // fait explicitement sur ce navigateur (nouvelle clé, ou ancienne clé pré-migration) n'est
      // réutilisé que s'il désigne une école qui existe réellement dans la liste ci-dessus.
      const stored = readStoredTenantContext();
      if (stored?.organizationId === organizationId && scoped.some((s) => s.id === stored.schoolId)) {
        setCurrentSchoolId(stored.schoolId);
        setCurrentSchool(scoped.find((s) => s.id === stored.schoolId) ?? null);
        setSchoolContextStatus("resolved");
        return;
      }
      const legacySchoolId = readLegacySchoolId();
      if (legacySchoolId && scoped.some((s) => s.id === legacySchoolId)) {
        setCurrentSchoolId(legacySchoolId);
        setCurrentSchool(scoped.find((s) => s.id === legacySchoolId) ?? null);
        setSchoolContextStatus("resolved");
        writeTenantContext({ organizationId, schoolId: legacySchoolId });
        return;
      }

      setCurrentSchool(null);
      setSchoolContextStatus("selection-needed");
    },
    [],
  );

  useEffect(() => {
    if (status !== "authenticated" || !me) return;
    const cancelledRef = { current: false };

    async function run() {
      const roles = me!.roles;

      // Compatibilité stricte : un compte explicitement lié à UNE SEULE école (jamais `roles[0]`
      // — un ensemble dédupliqué de taille 1) reste résolu directement, sans le moindre écran de
      // sélection, exactement comme avant cette phase.
      const fastPath = resolveSchoolScopedFastPath(roles);
      if (fastPath) {
        setAvailableOrganizations([]);
        setCurrentOrganizationId(fastPath.organizationId);
        setOrganizationContextStatus("resolved");
        setAvailableSchools([]);
        setCurrentSchoolId(fastPath.schoolId);
        setSchoolContextStatus("resolved");
        // `roles` ne porte que des identifiants (jamais de nom) : les objets complets sont
        // récupérés en tâche de fond, uniquement pour l'affichage (sélecteur de contexte) — sans
        // retarder ni conditionner la résolution ci-dessus, déjà terminée.
        void getOrganization(fastPath.organizationId)
          .then((org) => {
            if (!cancelledRef.current) setCurrentOrganization(org);
          })
          .catch(() => {});
        void getSchool(fastPath.schoolId)
          .then((school) => {
            if (!cancelledRef.current) setCurrentSchool(school);
          })
          .catch(() => {});
        return;
      }

      const orgIds = distinctOrganizationIds(roles);
      if (orgIds.length === 0) {
        // Ni rôle scopé école, ni rôle scopé organisation (ex. rôle plateforme, organization_id
        // ET school_id nuls) : aucun contexte de travail n'a de sens pour ce compte ici.
        setOrganizationContextStatus("empty");
        setSchoolContextStatus("empty");
        return;
      }

      if (orgIds.length === 1) {
        setAvailableOrganizations([]);
        setCurrentOrganizationId(orgIds[0]);
        setOrganizationContextStatus("resolved");
        // Même motif que ci-dessus : le nom de l'organisation n'est jamais nécessaire à la
        // résolution elle-même, seulement à son affichage.
        void getOrganization(orgIds[0])
          .then((org) => {
            if (!cancelledRef.current) setCurrentOrganization(org);
          })
          .catch(() => {});
        await resolveSchoolsForOrganization(orgIds[0], roles, cancelledRef);
        return;
      }

      // Plusieurs organisations réellement accessibles : jamais de choix implicite, quel que
      // soit l'ordre dans `roles`. La liste globale `GET /organizations` exige une permission
      // vérifiée SANS contexte (voir app/core/permissions.py::get_scoped_permission_codes) et ne
      // matche donc qu'un rôle réellement plateforme — jamais un rôle scopé à une organisation
      // précise (le cas ici). On récupère donc chaque organisation individuellement via
      // `GET /organizations/{id}` (déjà autorisé pour un rôle org-scoped), un appel par id connu
      // de `roles`, jamais une liste devinée.
      setOrganizationContextStatus("loading");
      setOrganizationContextError(null);
      const settled = await Promise.allSettled(orgIds.map((id) => getOrganization(id)));
      if (cancelledRef.current) return;

      const accessible: Organization[] = [];
      let firstError: unknown = null;
      for (const result of settled) {
        if (result.status === "fulfilled") accessible.push(result.value);
        else firstError ??= result.reason;
      }

      if (accessible.length === 0) {
        setOrganizationContextError(formatTenantContextError(firstError));
        setOrganizationContextStatus("error");
        return;
      }
      setAvailableOrganizations(accessible);

      if (accessible.length === 1) {
        setCurrentOrganizationId(accessible[0].id);
        setCurrentOrganization(accessible[0]);
        setOrganizationContextStatus("resolved");
        await resolveSchoolsForOrganization(accessible[0].id, roles, cancelledRef);
        return;
      }

      // Choix déjà fait explicitement sur ce navigateur, revalidé contre les organisations
      // réellement accessibles (jamais pris pour argent comptant) ET contre l'appartenance réelle
      // de l'école mémorisée à cette organisation (un couple {organizationId, schoolId} incohérent
      // n'est jamais réutilisé même partiellement — nouvelle sélection complète redemandée).
      const stored = readStoredTenantContext();
      if (stored && accessible.some((org) => org.id === stored.organizationId)) {
        const schoolValid = await isSchoolAccessibleInOrganization(stored.organizationId, stored.schoolId, roles);
        if (cancelledRef.current) return;
        if (schoolValid) {
          setCurrentOrganizationId(stored.organizationId);
          setCurrentOrganization(accessible.find((org) => org.id === stored.organizationId) ?? null);
          setOrganizationContextStatus("resolved");
          await resolveSchoolsForOrganization(stored.organizationId, roles, cancelledRef);
          return;
        }
      }

      // Ancienne clé (schoolId seul, sans organisation) : migration douce SEULEMENT si cette
      // école existe toujours et appartient à une organisation réellement accessible — jamais
      // devinée depuis les rôles seuls (un rôle org-wide ne mentionne aucun school_id précis),
      // confirmée directement auprès de l'API.
      const legacySchoolId = readLegacySchoolId();
      if (legacySchoolId) {
        const inferredOrgId = organizationIdForSchool(roles, legacySchoolId);
        let migratedOrgId = inferredOrgId && accessible.some((org) => org.id === inferredOrgId) ? inferredOrgId : null;
        if (!migratedOrgId) {
          try {
            const legacySchool = await getSchool(legacySchoolId);
            if (accessible.some((org) => org.id === legacySchool.organization_id)) {
              migratedOrgId = legacySchool.organization_id;
            }
          } catch {
            // École inaccessible/supprimée : jamais utilisée comme preuve, ignorée silencieusement.
          }
        }
        if (cancelledRef.current) return;
        if (migratedOrgId) {
          setCurrentOrganizationId(migratedOrgId);
          setCurrentOrganization(accessible.find((org) => org.id === migratedOrgId) ?? null);
          setOrganizationContextStatus("resolved");
          await resolveSchoolsForOrganization(migratedOrgId, roles, cancelledRef);
          return;
        }
      }

      setOrganizationContextStatus("selection-needed");
    }

    void run();
    return () => {
      cancelledRef.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, me, resolveAttempt, resolveSchoolsForOrganization]);

  const selectOrganization = useCallback(
    (organizationId: string) => {
      if (!me) return;
      // Défense en profondeur : le sélecteur ne propose jamais que des organisations déjà
      // vérifiées par l'API (`availableOrganizations`) — un id hors de cette liste (ne peut pas
      // arriver depuis l'UI actuelle, qui ne fait que mapper cette liste) est refusé plutôt que
      // d'être accepté tel quel.
      const organization = availableOrganizations.find((org) => org.id === organizationId);
      if (!organization) return;
      setCurrentOrganizationId(organizationId);
      setCurrentOrganization(organization);
      setOrganizationContextStatus("resolved");
      setCurrentSchoolId(null);
      setCurrentSchool(null);
      setAvailableSchools([]);
      const cancelledRef = { current: false };
      void resolveSchoolsForOrganization(organizationId, me.roles, cancelledRef);
    },
    [me, availableOrganizations, resolveSchoolsForOrganization],
  );

  const selectSchool = useCallback(
    (schoolId: string) => {
      // Même défense en profondeur que ci-dessus, côté école cette fois.
      const school = availableSchools.find((s) => s.id === schoolId);
      if (!school) return;
      if (currentOrganizationId) writeTenantContext({ organizationId: currentOrganizationId, schoolId });
      setCurrentSchoolId(schoolId);
      setCurrentSchool(school);
      setSchoolContextStatus("resolved");
    },
    [currentOrganizationId, availableSchools],
  );

  const retryTenantContext = useCallback(() => {
    setResolveAttempt((n) => n + 1);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: me?.user ?? null,
      roles: me?.roles ?? [],
      permissions: me?.permissions ?? [],
      currentOrganizationId,
      currentOrganization,
      organizationContextStatus,
      availableOrganizations,
      organizationContextError,
      selectOrganization,
      currentSchoolId,
      currentSchool,
      schoolContextStatus,
      availableSchools,
      schoolContextError,
      selectSchool,
      retryTenantContext,
      login,
      logout,
    }),
    [
      status,
      me,
      currentOrganizationId,
      currentOrganization,
      organizationContextStatus,
      availableOrganizations,
      organizationContextError,
      selectOrganization,
      currentSchoolId,
      currentSchool,
      schoolContextStatus,
      availableSchools,
      schoolContextError,
      selectSchool,
      retryTenantContext,
      login,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
