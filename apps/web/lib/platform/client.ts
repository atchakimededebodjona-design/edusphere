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
