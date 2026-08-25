import { apiFetch } from "@/lib/api/client";

export type AssessmentType = {
  id: string;
  school_id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type AssessmentTypeCreate = { school_id: string; name: string };

export type Assessment = {
  id: string;
  class_subject_id: string;
  academic_term_id: string;
  assessment_type_id: string;
  name: string;
  max_score: number;
  weight: number;
  assessment_date: string;
  created_at: string;
  updated_at: string;
};

export type AssessmentCreate = {
  class_subject_id: string;
  academic_term_id: string;
  assessment_type_id: string;
  name: string;
  max_score?: number;
  weight?: number;
  assessment_date: string;
};

export type AssessmentResult = {
  id: string;
  assessment_id: string;
  student_id: string;
  score: number | null;
  is_absent: boolean;
  created_at: string;
  updated_at: string;
};

export type AssessmentResultEntry = {
  student_id: string;
  score?: number | null;
  is_absent?: boolean;
};

export type StudentSubjectAverage = {
  id: string;
  student_id: string;
  class_subject_id: string;
  academic_term_id: string;
  average: number | null;
  rank: number | null;
  appreciation: string | null;
  updated_at: string;
};

export type StudentTermAverage = {
  id: string;
  student_id: string;
  academic_term_id: string;
  average: number | null;
  rank: number | null;
  updated_at: string;
};

export type StudentAverages = {
  subject_averages: StudentSubjectAverage[];
  term_averages: StudentTermAverage[];
};

export type ClassPerformanceEntry = {
  student_id: string;
  average: number | null;
  rank: number | null;
};

export type ClassPerformance = {
  academic_term_id: string;
  class_id: string;
  students: ClassPerformanceEntry[];
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

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

export const assessmentTypes = {
  list: (schoolId: string) => getJson<AssessmentType[]>(`/api/v1/assessment-types?school_id=${schoolId}`),
  create: (payload: AssessmentTypeCreate) => postJson<AssessmentType>("/api/v1/assessment-types", payload),
};

export const assessments = {
  list: (classSubjectId: string, academicTermId?: string) => {
    const params = new URLSearchParams({ class_subject_id: classSubjectId });
    if (academicTermId) params.set("academic_term_id", academicTermId);
    return getJson<Assessment[]>(`/api/v1/assessments?${params.toString()}`);
  },
  create: (payload: AssessmentCreate) => postJson<Assessment>("/api/v1/assessments", payload),
};

export const results = {
  list: (assessmentId: string) => getJson<AssessmentResult[]>(`/api/v1/results?assessment_id=${assessmentId}`),
  submit: (assessmentId: string, entries: AssessmentResultEntry[]) =>
    postJson<AssessmentResult[]>("/api/v1/results", { assessment_id: assessmentId, results: entries }),
  update: (resultId: string, payload: { score?: number | null; is_absent?: boolean }) =>
    patchJson<AssessmentResult>(`/api/v1/results/${resultId}`, payload),
};

export const studentAverages = {
  get: (studentId: string, academicTermId?: string) => {
    const params = academicTermId ? `?academic_term_id=${academicTermId}` : "";
    return getJson<StudentAverages>(`/api/v1/students/${studentId}/averages${params}`);
  },
};

export const subjectAverages = {
  updateAppreciation: (averageId: string, appreciation: string) =>
    patchJson<StudentSubjectAverage>(`/api/v1/student-subject-averages/${averageId}`, { appreciation }),
};

export const classPerformance = {
  get: (classId: string, academicTermId: string) =>
    getJson<ClassPerformance>(`/api/v1/classes/${classId}/performance?academic_term_id=${academicTermId}`),
};
