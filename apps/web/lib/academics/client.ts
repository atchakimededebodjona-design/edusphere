import { apiFetch } from "@/lib/api/client";

export type AcademicYear = {
  id: string;
  school_id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  created_at: string;
  updated_at: string;
};

export type AcademicYearCreate = {
  school_id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_current?: boolean;
};

export type AcademicYearUpdate = Partial<Omit<AcademicYearCreate, "school_id">>;

export type AcademicTerm = {
  id: string;
  academic_year_id: string;
  school_id: string;
  name: string;
  start_date: string;
  end_date: string;
  order_index: number;
  created_at: string;
  updated_at: string;
};

export type AcademicTermCreate = {
  academic_year_id: string;
  name: string;
  start_date: string;
  end_date: string;
  order_index?: number;
};

export type AcademicTermUpdate = Partial<Omit<AcademicTermCreate, "academic_year_id">>;

export type EducationLevel = {
  id: string;
  school_id: string;
  name: string;
  order_index: number;
  created_at: string;
  updated_at: string;
};

export type EducationLevelCreate = { school_id: string; name: string; order_index?: number };
export type EducationLevelUpdate = Partial<Omit<EducationLevelCreate, "school_id">>;

export type Subject = {
  id: string;
  school_id: string;
  name: string;
  code: string | null;
  created_at: string;
  updated_at: string;
};

export type SubjectCreate = { school_id: string; name: string; code?: string | null };
export type SubjectUpdate = Partial<Omit<SubjectCreate, "school_id">>;

export type Room = {
  id: string;
  school_id: string;
  name: string;
  capacity: number | null;
  created_at: string;
  updated_at: string;
};

export type RoomCreate = { school_id: string; name: string; capacity?: number | null };
export type RoomUpdate = Partial<Omit<RoomCreate, "school_id">>;

export type SchoolClass = {
  id: string;
  school_id: string;
  academic_year_id: string;
  education_level_id: string;
  name: string;
  capacity: number | null;
  created_at: string;
  updated_at: string;
};

export type SchoolClassCreate = {
  academic_year_id: string;
  education_level_id: string;
  name: string;
  capacity?: number | null;
};

export type ClassSubject = {
  id: string;
  class_id: string;
  subject_id: string;
  coefficient: number;
  created_at: string;
};

export type TeacherAssignment = {
  id: string;
  user_id: string;
  class_subject_id: string;
  created_at: string;
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

export const academicYears = {
  list: (schoolId: string) => getJson<AcademicYear[]>(`/api/v1/academic-years?school_id=${schoolId}`),
  create: (payload: AcademicYearCreate) => postJson<AcademicYear>("/api/v1/academic-years", payload),
  update: (id: string, payload: AcademicYearUpdate) => patchJson<AcademicYear>(`/api/v1/academic-years/${id}`, payload),
};

export const academicTerms = {
  list: (academicYearId: string) => getJson<AcademicTerm[]>(`/api/v1/academic-terms?academic_year_id=${academicYearId}`),
  create: (payload: AcademicTermCreate) => postJson<AcademicTerm>("/api/v1/academic-terms", payload),
  update: (id: string, payload: AcademicTermUpdate) => patchJson<AcademicTerm>(`/api/v1/academic-terms/${id}`, payload),
};

export const educationLevels = {
  list: (schoolId: string) => getJson<EducationLevel[]>(`/api/v1/education-levels?school_id=${schoolId}`),
  create: (payload: EducationLevelCreate) => postJson<EducationLevel>("/api/v1/education-levels", payload),
  update: (id: string, payload: EducationLevelUpdate) => patchJson<EducationLevel>(`/api/v1/education-levels/${id}`, payload),
};

export const subjects = {
  list: (schoolId: string) => getJson<Subject[]>(`/api/v1/subjects?school_id=${schoolId}`),
  create: (payload: SubjectCreate) => postJson<Subject>("/api/v1/subjects", payload),
  update: (id: string, payload: SubjectUpdate) => patchJson<Subject>(`/api/v1/subjects/${id}`, payload),
};

export const rooms = {
  list: (schoolId: string) => getJson<Room[]>(`/api/v1/rooms?school_id=${schoolId}`),
  create: (payload: RoomCreate) => postJson<Room>("/api/v1/rooms", payload),
  update: (id: string, payload: RoomUpdate) => patchJson<Room>(`/api/v1/rooms/${id}`, payload),
};

export const schoolClasses = {
  list: (schoolId: string) => getJson<SchoolClass[]>(`/api/v1/classes?school_id=${schoolId}`),
  create: (payload: SchoolClassCreate) => postJson<SchoolClass>("/api/v1/classes", payload),
};

export const classSubjects = {
  list: (classId: string) => getJson<ClassSubject[]>(`/api/v1/classes/${classId}/subjects`),
  create: (classId: string, payload: { subject_id: string; coefficient: number }) =>
    postJson<ClassSubject>(`/api/v1/classes/${classId}/subjects`, payload),
  remove: async (classId: string, classSubjectId: string): Promise<void> => {
    await apiFetch(`/api/v1/classes/${classId}/subjects/${classSubjectId}`, { method: "DELETE" });
  },
};

export const teacherAssignments = {
  list: (classId: string) => getJson<TeacherAssignment[]>(`/api/v1/classes/${classId}/teachers`),
  create: (classId: string, payload: { user_id: string; subject_id: string }) =>
    postJson<TeacherAssignment>(`/api/v1/classes/${classId}/teachers`, payload),
  remove: async (classId: string, assignmentId: string): Promise<void> => {
    await apiFetch(`/api/v1/classes/${classId}/teachers/${assignmentId}`, { method: "DELETE" });
  },
};
