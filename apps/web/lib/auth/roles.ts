import type { RoleAssignment } from "@/lib/auth/client";

// Phase 28A — un compte PARENT ne reçoit jamais de rôle admin/staff en plus (voir
// apps/api/app/modules/parent/router.py, "aucune permission RBAC vérifiée, seul le lien Guardian
// compte") : un compte dont TOUS les rôles sont PARENT n'a donc jamais rien à faire dans l'espace
// admin (`(app)`), qui suppose toujours au moins une permission scopée organisation/école. Un
// compte sans rôle du tout (ex. rôle plateforme) n'est PAS considéré "parent" ici — il reste géré
// par le flux existant (AuthGate, statut "empty").
export function isParentOnlyAccount(roles: RoleAssignment[]): boolean {
  return roles.length > 0 && roles.every((role) => role.role_code === "PARENT");
}

// Un compte peut cumuler un rôle PARENT et un rôle admin/staff (ex. un directeur qui est aussi
// tuteur de son propre enfant dans la même école) — ce compte a légitimement sa place dans les
// deux espaces. Utilisé par le portail parent (`(parent)/ParentGate.tsx`) pour ne rediriger vers
// l'espace admin QUE les comptes qui n'ont structurellement aucun rôle PARENT, jamais un compte
// mixte qui a explicitement navigué vers `/parent`.
export function hasAnyParentRole(roles: RoleAssignment[]): boolean {
  return roles.some((role) => role.role_code === "PARENT");
}
