import { apiFetch } from "@/lib/api/client";

export type AttendanceStatusValue = "PRESENT" | "ABSENT" | "LATE";

export type AttendanceSession = {
  id: string;
  class_id: string;
  academic_term_id: string;
  session_date: string;
  locked: boolean;
};

export type AttendanceRecord = {
  id: string;
  session_id: string;
  student_id: string;
  status: AttendanceStatusValue;
  justified: boolean;
  reason: string | null;
};

export type AttendanceRecordEntry = {
  student_id: string;
  status: AttendanceStatusValue;
  justified?: boolean;
  reason?: string | null;
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

export const attendanceSessions = {
  list: (classId: string, academicTermId: string, sessionDate: string) =>
    getJson<AttendanceSession[]>(
      `/api/v1/attendance-sessions?class_id=${classId}&academic_term_id=${academicTermId}&date_from=${sessionDate}&date_to=${sessionDate}`,
    ),
  create: (payload: { class_id: string; academic_term_id: string; session_date: string }) =>
    postJson<AttendanceSession>("/api/v1/attendance-sessions", payload),
};

export const attendanceRecords = {
  list: (sessionId: string) => getJson<AttendanceRecord[]>(`/api/v1/attendance-records?session_id=${sessionId}`),
  submit: (sessionId: string, records: AttendanceRecordEntry[]) =>
    postJson<AttendanceRecord[]>("/api/v1/attendance-records", { session_id: sessionId, records }),
};
