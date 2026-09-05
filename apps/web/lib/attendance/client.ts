import { apiFetch } from "@/lib/api/client";

export type AttendanceStatusValue = "PRESENT" | "ABSENT" | "LATE";

export type AttendanceSession = {
  id: string;
  school_id: string;
  class_id: string;
  academic_term_id: string;
  session_date: string;
  taken_by: string | null;
  locked: boolean;
  locked_at: string | null;
  locked_by: string | null;
  created_at: string;
  updated_at: string;
};

export type AttendanceSessionCreate = {
  class_id: string;
  academic_term_id: string;
  session_date: string;
};

export type AttendanceRecord = {
  id: string;
  session_id: string;
  student_id: string;
  status: AttendanceStatusValue;
  justified: boolean;
  reason: string | null;
  created_at: string;
  updated_at: string;
};

export type AttendanceRecordEntry = {
  student_id: string;
  status: AttendanceStatusValue;
  justified?: boolean;
  reason?: string | null;
};

export type AttendanceStudentSummary = {
  student_id: string;
  academic_term_id: string;
  total_sessions: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  justified_absence_count: number;
  attendance_rate: number | null;
};

export type AttendanceClassStudentStats = {
  student_id: string;
  total_sessions: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  justified_absence_count: number;
  attendance_rate: number | null;
};

export type AttendanceClassStatistics = {
  class_id: string;
  academic_term_id: string;
  students: AttendanceClassStudentStats[];
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

export const attendanceSessions = {
  list: (classId: string, filters: { academicTermId?: string; dateFrom?: string; dateTo?: string } = {}) => {
    const params = new URLSearchParams({ class_id: classId });
    if (filters.academicTermId) params.set("academic_term_id", filters.academicTermId);
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    return getJson<AttendanceSession[]>(`/api/v1/attendance-sessions?${params.toString()}`);
  },
  get: (id: string) => getJson<AttendanceSession>(`/api/v1/attendance-sessions/${id}`),
  create: (payload: AttendanceSessionCreate) => postJson<AttendanceSession>("/api/v1/attendance-sessions", payload),
  setLocked: (id: string, locked: boolean) => patchJson<AttendanceSession>(`/api/v1/attendance-sessions/${id}`, { locked }),
};

export const attendanceRecords = {
  list: (sessionId: string) => getJson<AttendanceRecord[]>(`/api/v1/attendance-records?session_id=${sessionId}`),
  submit: (sessionId: string, records: AttendanceRecordEntry[]) =>
    postJson<AttendanceRecord[]>("/api/v1/attendance-records", { session_id: sessionId, records }),
  update: (id: string, payload: { status?: AttendanceStatusValue; justified?: boolean; reason?: string | null }) =>
    patchJson<AttendanceRecord>(`/api/v1/attendance-records/${id}`, payload),
};

export const attendanceStats = {
  studentSummary: (studentId: string, academicTermId: string) =>
    getJson<AttendanceStudentSummary>(`/api/v1/students/${studentId}/attendance-summary?academic_term_id=${academicTermId}`),
  classStatistics: (classId: string, academicTermId: string) =>
    getJson<AttendanceClassStatistics>(`/api/v1/classes/${classId}/attendance-statistics?academic_term_id=${academicTermId}`),
};
