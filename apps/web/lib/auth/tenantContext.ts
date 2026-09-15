// Résolution du contexte multi-organisation/multi-école — logique pure, sans React ni fetch,
// pour rester lisible et vérifiable indépendamment de AuthProvider.tsx (qui l'orchestre).
//
// Règle centrale : ne jamais choisir une organisation ou une école arbitrairement (jamais
// `roles[0]`, jamais l'ordre du tableau, jamais `created_at`). Une organisation/école n'est
// retenue que si elle est UNIQUE parmi les rôles réels de l'utilisateur, ou explicitement
// choisie par lui — toujours revalidée contre ce que l'API renvoie réellement, jamais une
// valeur de localStorage prise pour argent comptant (le serveur reste l'autorité).

export type TenantRole = {
  role_code: string;
  organization_id: string | null;
  school_id: string | null;
};

export type TenantContext = {
  organizationId: string;
  schoolId: string;
};

function dedupe(values: (string | null)[]): string[] {
  const seen = new Set<string>();
  for (const value of values) if (value) seen.add(value);
  return [...seen];
}

export function distinctOrganizationIds(roles: TenantRole[]): string[] {
  return dedupe(roles.map((role) => role.organization_id));
}

export function distinctSchoolScopedIds(roles: TenantRole[]): string[] {
  return dedupe(roles.map((role) => role.school_id));
}

/** Organisation d'une école donnée, déduite des rôles qui la mentionnent explicitement — `null`
 * si aucun rôle ne porte ce `school_id` (ex. accès à cette école via un rôle org-wide, pas un
 * rôle scopé à cette école précise). */
export function organizationIdForSchool(roles: TenantRole[], schoolId: string): string | null {
  return roles.find((role) => role.school_id === schoolId && role.organization_id)?.organization_id ?? null;
}

/** Écoles auxquelles l'utilisateur a un rôle explicitement scopé, au sein d'une organisation
 * donnée (pas via un rôle org-wide qui verrait potentiellement d'autres écoles aussi). */
export function schoolScopedIdsForOrganization(roles: TenantRole[], organizationId: string): string[] {
  return dedupe(
    roles.filter((role) => role.organization_id === organizationId && role.school_id).map((role) => role.school_id),
  );
}

/** Compatibilité stricte avec le comportement historique : un compte explicitement lié à UNE
 * SEULE école (un ensemble dédupliqué de taille 1, jamais le premier rôle rencontré) reste
 * résolu directement, sans jamais afficher le moindre écran de sélection — c'est le cas de la
 * quasi-totalité des comptes (enseignant/personnel/parent/comptable à une seule école). Dès que
 * plusieurs écoles distinctes sont réellement rattachées, ce raccourci ne s'applique plus (voir
 * le flux général organisation -> école dans AuthProvider). */
export function resolveSchoolScopedFastPath(roles: TenantRole[]): TenantContext | null {
  const schoolIds = distinctSchoolScopedIds(roles);
  if (schoolIds.length !== 1) return null;
  const schoolId = schoolIds[0];
  const organizationId = organizationIdForSchool(roles, schoolId);
  if (!organizationId) return null;
  return { organizationId, schoolId };
}

// --- Persistance ---------------------------------------------------------------------------

const TENANT_CONTEXT_STORAGE_KEY = "edulinkage.tenant_context";
// Anciennes clés — ne stockaient qu'un schoolId, jamais l'organisation. Jamais utilisées comme
// preuve d'autorisation : voir AuthProvider, qui ne les exploite qu'après avoir confirmé,
// auprès de l'API, que l'école qu'elles désignent est toujours réellement accessible.
const LEGACY_SCHOOL_ID_STORAGE_KEYS = ["edulinkage.selected_school_id", "edusphere.selected_school_id"];

export function readStoredTenantContext(): TenantContext | null {
  const raw = window.localStorage.getItem(TENANT_CONTEXT_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<TenantContext>;
    if (typeof parsed.organizationId === "string" && typeof parsed.schoolId === "string") {
      return { organizationId: parsed.organizationId, schoolId: parsed.schoolId };
    }
  } catch {
    // JSON invalide (ex. contenu corrompu) : traité comme absent, jamais une erreur bloquante.
  }
  return null;
}

export function readLegacySchoolId(): string | null {
  for (const key of LEGACY_SCHOOL_ID_STORAGE_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value) return value;
  }
  return null;
}

export function writeTenantContext(context: TenantContext): void {
  window.localStorage.setItem(TENANT_CONTEXT_STORAGE_KEY, JSON.stringify(context));
  for (const key of LEGACY_SCHOOL_ID_STORAGE_KEYS) window.localStorage.removeItem(key);
}

export function clearLegacyTenantKeys(): void {
  for (const key of LEGACY_SCHOOL_ID_STORAGE_KEYS) window.localStorage.removeItem(key);
}
