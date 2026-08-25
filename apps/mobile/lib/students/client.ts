import { apiFetch } from "@/lib/api/client";

export type Student = {
  id: string;
  first_name: string;
  last_name: string;
  matricule: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

export const students = {
  list: (schoolId: string, classId: string) =>
    getJson<Student[]>(`/api/v1/students?school_id=${schoolId}&class_id=${classId}`),
};
