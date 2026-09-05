import { apiFetch } from "@/lib/api/client";

export type School = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  timezone: string;
  currency: string;
  logo_path: string | null;
  created_at: string;
  updated_at: string;
};

export type SchoolUpdate = Partial<
  Pick<School, "name" | "address" | "phone" | "email" | "timezone" | "currency">
>;

export async function getSchool(schoolId: string): Promise<School> {
  const response = await apiFetch(`/api/v1/schools/${schoolId}`);
  return response.json();
}

export async function listSchools(organizationId: string): Promise<School[]> {
  const response = await apiFetch(`/api/v1/schools?organization_id=${organizationId}`);
  return response.json();
}

export type SchoolDashboard = {
  active_student_count: number;
  attendance_rate: number | null;
  grade_completeness_rate: number | null;
  published_report_card_count: number;
  current_term_id: string | null;
  current_term_name: string | null;
};

export async function getSchoolDashboard(schoolId: string): Promise<SchoolDashboard> {
  const response = await apiFetch(`/api/v1/schools/${schoolId}/dashboard`);
  return response.json();
}

export async function updateSchool(schoolId: string, patch: SchoolUpdate): Promise<School> {
  const response = await apiFetch(`/api/v1/schools/${schoolId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return response.json();
}

export async function uploadSchoolLogo(schoolId: string, file: File): Promise<School> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiFetch(`/api/v1/schools/${schoolId}/logo`, {
    method: "POST",
    body: form,
  });
  return response.json();
}

export async function getSchoolLogoBlobUrl(schoolId: string): Promise<string | null> {
  try {
    const response = await apiFetch(`/api/v1/schools/${schoolId}/logo`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}
