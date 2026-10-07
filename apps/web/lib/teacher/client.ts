import { apiFetch, ApiError } from "@/lib/api/client";

// Client du portail enseignant. Toute donnée passe par /api/v1/teacher/* : le backend filtre
// selon TeacherAssignment (source de vérité). Le frontend n'applique aucun filtre de sécurité.

export type TeacherSchool = { id: string; name: string };

export type TeacherAnnouncement = { id: string; title: string; body: string; created_at: string; read: boolean };

export type TeacherMe = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  is_active: boolean;
  roles: string[];
  schools: TeacherSchool[];
};

export type TeacherSubject = {
  class_subject_id: string;
  subject_id: string;
  subject_name: string;
  coefficient: number;
};

export type TeacherClass = {
  id: string;
  name: string;
  school_id: string;
  academic_year_id: string;
  level_name: string | null;
  student_count: number;
  subjects: TeacherSubject[];
};

export type TeacherStudent = {
  id: string;
  matricule: string;
  first_name: string;
  last_name: string;
  status: string;
  class_id: string;
  class_name: string;
};

export type TeacherStudentDetail = {
  id: string;
  matricule: string;
  first_name: string;
  last_name: string;
  status: string;
  classes: { class_id: string; class_name: string }[];
};

export type TeacherAttendanceSession = {
  id: string;
  class_id: string;
  academic_term_id: string;
  session_date: string;
  locked: boolean;
  taken_by: string | null;
};

export type TeacherAssessment = {
  id: string;
  name: string;
  class_subject_id: string;
  subject_name: string;
  academic_term_id: string;
  max_score: number;
  assessment_date: string;
};

export type TeacherReportCard = {
  id: string;
  student_id: string;
  student_name: string;
  academic_term_id: string;
  status: string;
  published_at: string | null;
};

export type TeacherDashboard = {
  teacher_name: string;
  schools: TeacherSchool[];
  class_count: number;
  subject_count: number;
  student_count: number;
  recent_assessments: { id: string; name: string; class_name: string; subject_name: string; assessment_date: string }[];
  recent_notifications: { id: string; type: string; title: string; created_at: string; read: boolean }[];
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

export const teacherApi = {
  announcements: () => getJson<TeacherAnnouncement[]>("/api/v1/teacher/announcements"),
  me: () => getJson<TeacherMe>("/api/v1/teacher/me"),
  dashboard: () => getJson<TeacherDashboard>("/api/v1/teacher/dashboard"),
  classes: () => getJson<TeacherClass[]>("/api/v1/teacher/classes"),
  classDetail: (classId: string) => getJson<TeacherClass>(`/api/v1/teacher/classes/${classId}`),
  classStudents: (classId: string, search?: string) =>
    getJson<TeacherStudent[]>(`/api/v1/teacher/classes/${classId}/students${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  students: (params: { classId?: string; search?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.classId) q.set("class_id", params.classId);
    if (params.search) q.set("search", params.search);
    const query = q.toString();
    return getJson<TeacherStudent[]>(`/api/v1/teacher/students${query ? `?${query}` : ""}`);
  },
  student: (studentId: string) => getJson<TeacherStudentDetail>(`/api/v1/teacher/students/${studentId}`),
  attendanceSessions: (classId: string) =>
    getJson<TeacherAttendanceSession[]>(`/api/v1/teacher/classes/${classId}/attendance-sessions`),
  assessments: (classId: string) => getJson<TeacherAssessment[]>(`/api/v1/teacher/classes/${classId}/assessments`),
  reportCards: (classId: string) => getJson<TeacherReportCard[]>(`/api/v1/teacher/classes/${classId}/report-cards`),
  reportCardPdf: async (reportCardId: string): Promise<Blob> => {
    const response = await apiFetch(`/api/v1/teacher/report-cards/${reportCardId}/pdf`);
    return response.blob();
  },
};

export function describeTeacherError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Cet espace est réservé aux enseignants de l'école.";
    if (err.status === 404) return "Cette ressource n'est pas accessible avec votre affectation.";
    if (err.status >= 500) return "Une erreur serveur est survenue. Réessayez.";
    return err.message;
  }
  return "Une erreur est survenue.";
}
