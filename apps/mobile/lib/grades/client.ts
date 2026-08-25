import { apiFetch } from "@/lib/api/client";

export type Assessment = {
  id: string;
  class_subject_id: string;
  academic_term_id: string;
  assessment_type_id: string;
  name: string;
  max_score: number;
  weight: number;
  assessment_date: string;
};

export type AssessmentResult = {
  id: string;
  assessment_id: string;
  student_id: string;
  score: number | null;
  is_absent: boolean;
};

export type AssessmentResultEntry = {
  student_id: string;
  score?: number | null;
  is_absent?: boolean;
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

export const assessments = {
  list: (classSubjectId: string, academicTermId: string) =>
    getJson<Assessment[]>(`/api/v1/assessments?class_subject_id=${classSubjectId}&academic_term_id=${academicTermId}`),
};

export const results = {
  list: (assessmentId: string) => getJson<AssessmentResult[]>(`/api/v1/results?assessment_id=${assessmentId}`),
  submit: (assessmentId: string, entries: AssessmentResultEntry[]) =>
    postJson<AssessmentResult[]>("/api/v1/results", { assessment_id: assessmentId, results: entries }),
};
