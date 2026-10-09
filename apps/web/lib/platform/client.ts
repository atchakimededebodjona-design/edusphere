import { apiFetch } from "@/lib/api/client";

export type PlatformDashboard = {
  organization_count: number;
  school_count: number;
  user_count: number;
  student_count: number;
  // PR #17
  partner_count: number;
  enrollment_count: number;
};

export async function getPlatformDashboard(): Promise<PlatformDashboard> {
  const response = await apiFetch("/api/v1/platform/dashboard");
  return response.json();
}

// Création d'organisation — réservée aux platform admins (contrôle côté backend :
// apps/api/app/modules/platform/router.py::create_platform_organization). Le School Admin créé
// n'est jamais connecté dans la session du platform admin.
export type PlatformOrganizationInput = {
  name: string;
  slug: string;
  country_code: string;
  timezone: string;
  currency: string;
};

export type PlatformSchoolInput = {
  name: string;
  slug: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  timezone: string;
  currency: string;
};

export type PlatformAdminInput = {
  full_name: string;
  email: string;
  phone: string | null;
  password: string;
};

export type PlatformOrganizationCreate = {
  organization: PlatformOrganizationInput;
  school: PlatformSchoolInput;
  admin: PlatformAdminInput;
};

export type PlatformOrganizationCreated = {
  organization: { id: string; name: string; slug: string; country_code: string; timezone: string; currency: string };
  school: { id: string; organization_id: string; name: string; slug: string };
  admin: { id: string; email: string; full_name: string; is_platform_admin: boolean };
  admin_role_code: string;
};

export async function createPlatformOrganization(
  payload: PlatformOrganizationCreate,
): Promise<PlatformOrganizationCreated> {
  const response = await apiFetch("/api/v1/platform/organizations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

// --- PR #17 — lectures plateforme (métadonnées uniquement) et partenaires --------------------
// Chaque endpoint exige une permission `platform.*` vérifiée côté API (apps/api/app/modules/
// platform/router.py) — ce client ne fait que les appeler.

export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type PlatformOrganization = {
  id: string;
  name: string;
  slug: string;
  country_code: string;
  created_at: string;
};

export type AcquisitionSource = "PLATFORM_OWNER" | "PARTNER";

export type PlatformSchool = {
  id: string;
  name: string;
  organization_id: string;
  slug: string;
  created_at: string;
  acquisition_source: AcquisitionSource | null;
};

export type PlatformAccount = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  role_codes: string[];
};

export type PlatformPartner = {
  id: string;
  user_id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  status: string;
  created_at: string;
  enrollment_count: number;
};

export type PlatformPartnerCreate = {
  display_name: string;
  full_name: string;
  email: string;
  phone: string | null;
};

export type PlatformPartnerCreated = {
  partner: PlatformPartner;
  dev_reset_token: string | null;
};

function pageQuery(page: number, pageSize: number): string {
  return `?page=${encodeURIComponent(String(page))}&page_size=${encodeURIComponent(String(pageSize))}`;
}

export async function listPlatformOrganizations(page = 1, pageSize = 20): Promise<Page<PlatformOrganization>> {
  const response = await apiFetch(`/api/v1/platform/organizations${pageQuery(page, pageSize)}`);
  return response.json();
}

export async function listPlatformSchools(page = 1, pageSize = 20): Promise<Page<PlatformSchool>> {
  const response = await apiFetch(`/api/v1/platform/schools${pageQuery(page, pageSize)}`);
  return response.json();
}

export async function listPlatformAccounts(page = 1, pageSize = 20): Promise<Page<PlatformAccount>> {
  const response = await apiFetch(`/api/v1/platform/accounts${pageQuery(page, pageSize)}`);
  return response.json();
}

export async function listPlatformPartners(page = 1, pageSize = 20): Promise<Page<PlatformPartner>> {
  const response = await apiFetch(`/api/v1/platform/partners${pageQuery(page, pageSize)}`);
  return response.json();
}

export async function createPlatformPartner(payload: PlatformPartnerCreate): Promise<PlatformPartnerCreated> {
  const response = await apiFetch("/api/v1/platform/partners", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}
