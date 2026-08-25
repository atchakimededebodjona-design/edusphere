import { API_URL, apiFetch } from "@/lib/api/client";

export type ReportCardStatus = "DRAFT" | "PUBLISHED";

export type ReportCardTemplate = {
  id: string;
  school_id: string;
  name: string;
  html_content: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type ReportCardTemplateCreate = {
  school_id: string;
  name: string;
  html_content: string;
  is_default?: boolean;
};

export type ReportCard = {
  id: string;
  student_id: string;
  class_id: string;
  academic_term_id: string;
  template_id: string;
  status: ReportCardStatus;
  verification_code: string;
  general_average: number | null;
  general_rank: number | null;
  generated_at: string;
  published_at: string | null;
};

export type ReportCardVerify = {
  school_name: string;
  student_full_name: string;
  class_name: string;
  academic_term_name: string;
  general_average: number | null;
  general_rank: number | null;
  status: ReportCardStatus;
  generated_at: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

export const templates = {
  list: (schoolId: string) => getJson<ReportCardTemplate[]>(`/api/v1/report-card-templates?school_id=${schoolId}`),
  create: (payload: ReportCardTemplateCreate) => postJson<ReportCardTemplate>("/api/v1/report-card-templates", payload),
};

export const reportCards = {
  list: (classId: string, academicTermId: string) =>
    getJson<ReportCard[]>(`/api/v1/report-cards?class_id=${classId}&academic_term_id=${academicTermId}`),
  generate: (payload: { class_id: string; academic_term_id: string; template_id: string }) =>
    postJson<ReportCard[]>("/api/v1/report-cards/generate", payload),
  publish: (id: string) => postJson<ReportCard>(`/api/v1/report-cards/${id}/publish`, {}),
  download: async (reportCard: ReportCard, studentLabel: string): Promise<void> => {
    const response = await apiFetch(`/api/v1/report-cards/${reportCard.id}/pdf`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bulletin_${studentLabel}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },
};

export async function verify(code: string): Promise<ReportCardVerify> {
  const response = await fetch(`${API_URL}/api/v1/report-cards/verify/${code}`);
  if (!response.ok) throw new Error(response.status === 404 ? "not_found" : "error");
  return response.json();
}
