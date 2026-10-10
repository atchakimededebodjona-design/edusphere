import { apiFetch } from "@/lib/api/client";
import type { PlatformOrganizationCreate, SchoolAddPayload, SchoolAdded } from "@/lib/platform/client";

// PR #17 — espace partenaire. Aucun identifiant de partenaire n'est jamais envoyé : l'API le
// dérive du compte authentifié (apps/api/app/modules/partners/service.py::get_own_partner) et
// rejette (422) tout champ `partner_id` dans le corps d'une inscription.

export type PartnerDashboard = {
  school_count: number;
  organization_count: number;
};

export type PartnerSchool = {
  school_id: string;
  school_name: string;
  organization_id: string;
  organization_name: string;
  enrolled_at: string;
  status: string;
  // Agrégats uniquement (COUNT côté API) — jamais de donnée individuelle d'élève.
  student_count: number;
  active_student_count: number;
};

export type PartnerAccount = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  role_codes: string[];
};

// Même contenu que l'inscription plateforme (organisation, école, premier SCHOOL_ADMIN).
export type PartnerSchoolEnrollCreate = PlatformOrganizationCreate;

export type PartnerSchoolEnrolled = {
  organization: { id: string; name: string; slug: string };
  school: { id: string; organization_id: string; name: string; slug: string };
  admin: { id: string; email: string; full_name: string };
  admin_role_code: string;
  acquisition_source: string;
  commission_eligible: boolean;
};

export async function getPartnerDashboard(): Promise<PartnerDashboard> {
  const response = await apiFetch("/api/v1/partner/dashboard");
  return response.json();
}

export async function listPartnerSchools(): Promise<PartnerSchool[]> {
  const response = await apiFetch("/api/v1/partner/schools");
  return response.json();
}

export async function enrollPartnerSchool(payload: PartnerSchoolEnrollCreate): Promise<PartnerSchoolEnrolled> {
  const response = await apiFetch("/api/v1/partner/schools", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function listPartnerAccounts(): Promise<PartnerAccount[]> {
  const response = await apiFetch("/api/v1/partner/accounts");
  return response.json();
}

// --- PR #19 — organisations du périmètre du partenaire -------------------------------------------
// Uniquement les organisations où CE partenaire a déjà au moins une école inscrite (filtrage côté
// API) ; l'ajout d'un établissement hors de ce périmètre est refusé par l'API (404).
export type PartnerOrganization = {
  organization_id: string;
  organization_name: string;
  schools: PartnerSchool[];
};

export async function listPartnerOrganizations(): Promise<PartnerOrganization[]> {
  const response = await apiFetch("/api/v1/partner/organizations");
  return response.json();
}

export async function addPartnerSchool(organizationId: string, payload: SchoolAddPayload): Promise<SchoolAdded> {
  const response = await apiFetch(`/api/v1/partner/organizations/${encodeURIComponent(organizationId)}/schools`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}
