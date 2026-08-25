import { apiFetch } from "@/lib/api/client";

export type SchoolClass = {
  id: string;
  school_id: string;
  academic_year_id: string;
  education_level_id: string;
  name: string;
  capacity: number | null;
};

export type AcademicTerm = {
  id: string;
  academic_year_id: string;
  school_id: string;
  name: string;
  start_date: string;
  end_date: string;
  order_index: number;
};

export type Subject = {
  id: string;
  school_id: string;
  name: string;
  code: string | null;
};

export type ClassSubject = {
  id: string;
  class_id: string;
  subject_id: string;
  coefficient: number;
};

export type TeacherAssignment = {
  id: string;
  user_id: string;
  class_subject_id: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

export const schoolClasses = {
  list: (schoolId: string) => getJson<SchoolClass[]>(`/api/v1/classes?school_id=${schoolId}`),
  get: (classId: string) => getJson<SchoolClass>(`/api/v1/classes/${classId}`),
};

export const academicTerms = {
  list: (academicYearId: string) => getJson<AcademicTerm[]>(`/api/v1/academic-terms?academic_year_id=${academicYearId}`),
};

export const subjects = {
  list: (schoolId: string) => getJson<Subject[]>(`/api/v1/subjects?school_id=${schoolId}`),
};

export const classSubjects = {
  list: (classId: string) => getJson<ClassSubject[]>(`/api/v1/classes/${classId}/subjects`),
};

export const teacherAssignments = {
  list: (classId: string) => getJson<TeacherAssignment[]>(`/api/v1/classes/${classId}/teachers`),
};
