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
  // Renseignés uniquement par students.list(), pour l'année scolaire courante de l'école — null si
  // aucune année n'est marquée courante, ou si l'élève n'y a aucune inscription active (voir
  // students/router.py::list_students, qui distingue ces deux cas pour le frontend).
  current_class_id: string | null;
  current_class_name: string | null;
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
  // Sprint 1.11 — compte utilisateur PARENT lié (backend : GuardianOut.user_id, déjà renvoyé par
  // l'API depuis la Phase 7 ; simplement jamais déclaré côté web jusqu'ici).
  user_id: string | null;
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
export type PromotionType = "PROMOTED" | "REPEATED" | "TRANSFERRED";

export type StudentEnrollment = {
  id: string;
  student_id: string;
  class_id: string;
  academic_year_id: string;
  enrollment_date: string;
  status: EnrollmentStatus;
  promotion_type: PromotionType | null;
  created_at: string;
  updated_at: string;
};

export type StudentDocument = {
  id: string;
  student_id: string;
  document_type: string;
  file_path: string;
  original_filename: string;
  mime_type: string | null;
  file_size: number | null;
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

// Modification en masse — STATUT uniquement (voir students/schemas.py::StudentBulkStatusUpdate) :
// les champs individuels (identité, date de naissance, sexe) ne sont délibérément pas proposés ici.
export type StudentBulkStatusUpdate = {
  student_ids: string[];
  status: StudentStatus;
  status_change_reason?: string;
};

export type StudentBulkUpdateResult = {
  updated_count: number;
  unchanged_count: number;
  students: Student[];
};

// Affectation en masse à une classe (voir students/schemas.py::StudentBulkEnrollmentCreate/Out).
export type StudentBulkEnrollmentCreate = {
  student_ids: string[];
  academic_year_id: string;
  class_id: string;
  enrollment_date: string;
};

export type StudentBulkEnrollmentResult = {
  target_class_id: string;
  target_class_name: string;
  academic_year_id: string;
  capacity: number | null;
  active_enrollment_count: number;
  available_places: number | null;
  selected_count: number;
  created_count: number;
  reassigned_count: number;
  unchanged_count: number;
  students: Student[];
};

// Réinscription / promotion en masse (voir students/schemas.py::StudentBulkPromotionCreate/Out).
export type ClassMapping = { source_class_id: string; target_class_id: string };

// Sortie de l'établissement (voir students/schemas.py::StudentExitDisposition/Out). Une classe
// source ne doit JAMAIS apparaître à la fois dans class_mappings ET exit_dispositions.
export type ExitType = "GRADUATED" | "TRANSFERRED" | "WITHDRAWN" | "OTHER";

export type StudentExitDisposition = {
  source_class_id: string;
  exit_type: ExitType;
  reason?: string | null;
};

export type StudentExitOut = {
  id: string;
  student_id: string;
  academic_year_id: string;
  exit_type: ExitType;
  reason: string | null;
  exit_date: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type StudentBulkPromotionCreate = {
  source_academic_year_id: string;
  target_academic_year_id: string;
  class_mappings: ClassMapping[];
  exit_dispositions: StudentExitDisposition[];
  student_ids: string[];
  enrollment_date: string;
};

export type TargetClassPreview = {
  target_class_id: string;
  target_class_name: string;
  capacity: number | null;
  active_enrollment_count: number;
  incoming_count: number;
  available_places: number | null;
};

export type StudentBulkPromotionResult = {
  source_academic_year_id: string;
  target_academic_year_id: string;
  selected_count: number;
  promoted_count: number;
  repeated_count: number;
  already_enrolled_count: number;
  no_target_class_count: number;
  exit_count: number;
  unprocessed_no_target_class_count: number;
  exit_counts_by_type: Record<string, number>;
  class_previews: TargetClassPreview[];
  blocking_errors: string[];
  students: Student[];
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
  list: (
    schoolId: string,
    filters: { search?: string; classId?: string; status?: StudentStatus; unassignedOnly?: boolean } = {},
  ) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (filters.search) params.set("search", filters.search);
    if (filters.classId) params.set("class_id", filters.classId);
    if (filters.status) params.set("status", filters.status);
    if (filters.unassignedOnly) params.set("unassigned_only", "true");
    return getJson<Student[]>(`/api/v1/students?${params.toString()}`);
  },
  get: (id: string) => getJson<Student>(`/api/v1/students/${id}`),
  create: (payload: StudentCreate) => postJson<Student>("/api/v1/students", payload),
  update: (id: string, payload: StudentUpdate) => patchJson<Student>(`/api/v1/students/${id}`, payload),
  bulkUpdateStatus: (payload: StudentBulkStatusUpdate) =>
    patchJson<StudentBulkUpdateResult>("/api/v1/students/bulk", payload),
  // `dryRun: true` calcule et renvoie l'aperçu (capacité, répartition nouveaux/réaffectés/
  // inchangés) sans rien écrire en base — voir students/router.py::bulk_enroll_students.
  bulkEnroll: (payload: StudentBulkEnrollmentCreate, dryRun = false) =>
    postJson<StudentBulkEnrollmentResult>(`/api/v1/students/bulk-enrollment?dry_run=${dryRun}`, payload),
  bulkPromote: (payload: StudentBulkPromotionCreate, dryRun = false) =>
    postJson<StudentBulkPromotionResult>(`/api/v1/students/bulk-promotion?dry_run=${dryRun}`, payload),
  uploadPhoto: async (id: string, file: File): Promise<Student> => {
    const form = new FormData();
    form.append("file", file);
    const response = await apiFetch(`/api/v1/students/${id}/photo`, { method: "POST", body: form });
    return response.json();
  },
  getPhotoBlobUrl: (id: string) => getBlobUrl(`/api/v1/students/${id}/photo`),
  deletePhoto: async (id: string): Promise<void> => {
    await apiFetch(`/api/v1/students/${id}/photo`, { method: "DELETE" });
  },
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
  // Sprint 1.11 — lie ce Guardian à un compte utilisateur PARENT existant. Endpoint backend déjà
  // existant et validé (PATCH /guardians/{id}) : l'appelant doit déjà avoir un rôle PARENT dans
  // cette école, sinon le backend refuse (400) — jamais vérifié ici, le backend reste l'autorité.
  update: (guardianId: string, payload: { user_id: string }) =>
    patchJson<Guardian>(`/api/v1/guardians/${guardianId}`, payload),
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

export const studentExits = {
  listForStudent: (studentId: string) => getJson<StudentExitOut[]>(`/api/v1/students/${studentId}/exits`),
  listForSchool: (schoolId: string) => getJson<StudentExitOut[]>(`/api/v1/student-exits?school_id=${schoolId}`),
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
