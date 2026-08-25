import { apiFetch } from "@/lib/api/client";

export type StudentStatus = "ACTIVE" | "INACTIVE" | "GRADUATED" | "WITHDRAWN" | "TRANSFERRED";
export type Sex = "M" | "F";

export type Student = {
  id: string;
  school_id: string;
  matricule: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  sex: Sex;
  place_of_birth: string | null;
  address: string | null;
  status: StudentStatus;
  photo_path: string | null;
  created_at: string;
  updated_at: string;
};

export type StudentCreate = {
  school_id: string;
  matricule: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  sex: Sex;
  place_of_birth?: string | null;
  address?: string | null;
};

export type StudentUpdate = Partial<Omit<StudentCreate, "school_id">> & {
  status?: StudentStatus;
  status_change_reason?: string;
};

export type GuardianRelationship = "father" | "mother" | "guardian" | "other";

export type Guardian = {
  id: string;
  school_id: string;
  full_name: string;
  relationship_type: GuardianRelationship;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_emergency_contact: boolean;
  created_at: string;
  updated_at: string;
};

export type GuardianCreate = {
  school_id: string;
  full_name: string;
  relationship_type: GuardianRelationship;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  is_emergency_contact?: boolean;
};

export type StudentGuardian = {
  id: string;
  student_id: string;
  guardian_id: string;
  is_primary_contact: boolean;
  created_at: string;
};

export type EnrollmentStatus = "ACTIVE" | "WITHDRAWN" | "TRANSFERRED" | "COMPLETED";

export type StudentEnrollment = {
  id: string;
  student_id: string;
  class_id: string;
  academic_year_id: string;
  enrollment_date: string;
  status: EnrollmentStatus;
  created_at: string;
  updated_at: string;
};

export type StudentDocument = {
  id: string;
  student_id: string;
  document_type: string;
  file_path: string;
  original_filename: string;
  uploaded_by: string | null;
  created_at: string;
};

export type StudentImportRowError = { row: number; reason: string };

export type StudentImportReport = {
  total_rows: number;
  created: number;
  duplicates_skipped: number;
  errors: StudentImportRowError[];
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

async function getBlobUrl(path: string): Promise<string | null> {
  try {
    const response = await apiFetch(path);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

export const students = {
  list: (schoolId: string, filters: { search?: string; classId?: string; status?: StudentStatus } = {}) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (filters.search) params.set("search", filters.search);
    if (filters.classId) params.set("class_id", filters.classId);
    if (filters.status) params.set("status", filters.status);
    return getJson<Student[]>(`/api/v1/students?${params.toString()}`);
  },
  get: (id: string) => getJson<Student>(`/api/v1/students/${id}`),
  create: (payload: StudentCreate) => postJson<Student>("/api/v1/students", payload),
  update: (id: string, payload: StudentUpdate) => patchJson<Student>(`/api/v1/students/${id}`, payload),
  uploadPhoto: async (id: string, file: File): Promise<Student> => {
    const form = new FormData();
    form.append("file", file);
    const response = await apiFetch(`/api/v1/students/${id}/photo`, { method: "POST", body: form });
    return response.json();
  },
  getPhotoBlobUrl: (id: string) => getBlobUrl(`/api/v1/students/${id}/photo`),
  import: async (schoolId: string, file: File): Promise<StudentImportReport> => {
    const form = new FormData();
    form.append("school_id", schoolId);
    form.append("file", file);
    const response = await apiFetch("/api/v1/students/import", { method: "POST", body: form });
    return response.json();
  },
};

export const guardians = {
  list: (schoolId: string) => getJson<Guardian[]>(`/api/v1/guardians?school_id=${schoolId}`),
  create: (payload: GuardianCreate) => postJson<Guardian>("/api/v1/guardians", payload),
};

export const studentGuardians = {
  list: (studentId: string) => getJson<StudentGuardian[]>(`/api/v1/students/${studentId}/guardians`),
  attach: (studentId: string, payload: { guardian_id: string; is_primary_contact?: boolean }) =>
    postJson<StudentGuardian>(`/api/v1/students/${studentId}/guardians`, payload),
  detach: async (studentId: string, linkId: string): Promise<void> => {
    await apiFetch(`/api/v1/students/${studentId}/guardians/${linkId}`, { method: "DELETE" });
  },
};

export const enrollments = {
  list: (studentId: string) => getJson<StudentEnrollment[]>(`/api/v1/students/${studentId}/enrollments`),
  create: (studentId: string, payload: { class_id: string; enrollment_date: string }) =>
    postJson<StudentEnrollment>(`/api/v1/students/${studentId}/enrollments`, payload),
  updateStatus: (enrollmentId: string, status: EnrollmentStatus) =>
    patchJson<StudentEnrollment>(`/api/v1/enrollments/${enrollmentId}`, { status }),
};

export const documents = {
  list: (studentId: string) => getJson<StudentDocument[]>(`/api/v1/students/${studentId}/documents`),
  upload: async (studentId: string, documentType: string, file: File): Promise<StudentDocument> => {
    const form = new FormData();
    form.append("document_type", documentType);
    form.append("file", file);
    const response = await apiFetch(`/api/v1/students/${studentId}/documents`, { method: "POST", body: form });
    return response.json();
  },
  remove: async (studentId: string, documentId: string): Promise<void> => {
    await apiFetch(`/api/v1/students/${studentId}/documents/${documentId}`, { method: "DELETE" });
  },
  download: async (studentId: string, doc: StudentDocument): Promise<void> => {
    const response = await apiFetch(`/api/v1/students/${studentId}/documents/${doc.id}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = doc.original_filename;
    link.click();
    URL.revokeObjectURL(url);
  },
};
