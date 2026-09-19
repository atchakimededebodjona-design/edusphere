import { apiFetch } from "@/lib/api/client";
import type { FinancialSummary, Payment } from "@/lib/fees/client";
import type { StudentAverages } from "@/lib/grades/client";
import type { ReportCard } from "@/lib/report-cards/client";
import type { Student } from "@/lib/students/client";

// Phase 28A — Portail Parent Web. Consomme exclusivement les endpoints `/api/v1/parent/*` déjà
// existants et testés (apps/api/app/modules/parent, apps/api/tests/test_parent.py) : chaque appel
// ci-dessous revalide lui-même, côté serveur, que l'élève ciblé est réellement un enfant de
// l'utilisateur courant (voir parent/router.py::_get_child_or_404) — un `student_id` dans l'URL
// n'est donc jamais une preuve d'autorisation côté client, seulement un paramètre de route.
//
// Types réutilisés tels quels depuis les clients existants quand le backend renvoie exactement le
// même schéma (StudentOut, StudentAveragesOut, ReportCardOut, FinancialSummaryOut, PaymentOut) —
// voir apps/api/app/modules/parent/router.py, `response_model=...`.

export type ParentAttendanceSummary = {
  student_id: string;
  academic_term_id: string | null;
  total_sessions: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  justified_absence_count: number;
  attendance_rate: number | null;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

async function getBlobUrl(path: string): Promise<string> {
  const response = await apiFetch(path);
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export const parentChildren = {
  list: () => getJson<Student[]>("/api/v1/parent/children"),

  // `academic_term_id` volontairement omis (jamais envoyé) : le portail web parent, comme le
  // mobile parent, n'a pas de sélecteur de période — l'API renvoie alors un agrégat toutes
  // périodes confondues (voir ParentAttendanceSummaryOut, parent/schemas.py).
  attendanceSummary: (studentId: string) =>
    getJson<ParentAttendanceSummary>(`/api/v1/parent/children/${studentId}/attendance-summary`),

  grades: (studentId: string) => getJson<StudentAverages>(`/api/v1/parent/children/${studentId}/grades`),

  reportCards: (studentId: string) => getJson<ReportCard[]>(`/api/v1/parent/children/${studentId}/report-cards`),

  downloadReportCardPdf: async (studentId: string, reportCard: ReportCard, studentLabel: string): Promise<void> => {
    const url = await getBlobUrl(`/api/v1/parent/children/${studentId}/report-cards/${reportCard.id}/pdf`);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bulletin_${studentLabel}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },

  fees: (studentId: string) => getJson<FinancialSummary>(`/api/v1/parent/children/${studentId}/fees`),

  payments: (studentId: string) => getJson<Payment[]>(`/api/v1/parent/children/${studentId}/payments`),

  getReceiptBlobUrl: (studentId: string, paymentId: string) =>
    getBlobUrl(`/api/v1/parent/children/${studentId}/payments/${paymentId}/receipt.pdf`),
};
