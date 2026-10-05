import { apiFetch } from "@/lib/api/client";

export type PlatformDashboard = {
  organization_count: number;
  school_count: number;
  user_count: number;
  student_count: number;
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
