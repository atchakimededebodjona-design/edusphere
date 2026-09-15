import { apiFetch } from "@/lib/api/client";

export type Organization = {
  id: string;
  name: string;
  slug: string;
  country_code: string;
  timezone: string;
  currency: string;
  created_at: string;
  updated_at: string;
};

// Sélection multi-organisation — `GET /api/v1/organizations/{id}` (singulier, déjà existant :
// apps/api/app/modules/organizations/router.py::get_organization) plutôt que la liste globale
// `GET /api/v1/organizations` : cette dernière exige `organizations.read` vérifiée SANS contexte
// (`require_permission`, voir app/core/permissions.py::get_scoped_permission_codes) — elle ne
// matche donc qu'un rôle réellement PLATEFORME (organization_id ET school_id nuls), jamais un
// SCHOOL_ADMIN scopé à une ou plusieurs organisations précises (le cas visé ici). L'endpoint
// singulier, lui, vérifie la permission AVEC `organization_id` (`ensure_permission(...,
// organization_id=organization.id)`), qui matche correctement un rôle org-scoped pour CETTE
// organisation. Chaque organisation à afficher est de toute façon déjà connue côté client (issue
// de `me.roles`), jamais devinée — un appel par organisation, jamais une liste globale.
export async function getOrganization(organizationId: string): Promise<Organization> {
  const response = await apiFetch(`/api/v1/organizations/${organizationId}`);
  return response.json();
}
