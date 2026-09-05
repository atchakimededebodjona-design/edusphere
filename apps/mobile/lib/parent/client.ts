import * as FileSystem from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";
import { API_URL, ApiError, apiFetch, refreshTokens } from "@/lib/api/client";
import { getStoredTokens } from "@/lib/auth/session";

export type Child = {
  id: string;
  first_name: string;
  last_name: string;
  matricule: string;
  photo_path: string | null;
};

export type AttendanceSummary = {
  student_id: string;
  academic_term_id: string | null;
  total_sessions: number;
  present_count: number;
  absent_count: number;
  late_count: number;
  justified_absence_count: number;
  attendance_rate: number | null;
};

export type SubjectAverage = {
  id: string;
  class_subject_id: string;
  academic_term_id: string;
  average: number | null;
  rank: number | null;
  appreciation: string | null;
};

export type TermAverage = {
  id: string;
  academic_term_id: string;
  average: number | null;
  rank: number | null;
};

export type StudentAverages = {
  subject_averages: SubjectAverage[];
  term_averages: TermAverage[];
};

export type ReportCard = {
  id: string;
  academic_term_id: string;
  status: "DRAFT" | "PUBLISHED";
  general_average: number | null;
  general_rank: number | null;
  generated_at: string;
  published_at: string | null;
};

// --- Frais scolaires (Phase 19) — lecture seule uniquement, voir PHASE_19_DISCOVERY.md §21.
export type StudentFeeStatus = "PENDING" | "PARTIALLY_PAID" | "PAID" | "CANCELLED";

export type StudentFeeWithBalance = {
  id: string;
  fee_schedule_name: string;
  amount_due: string;
  amount_paid: string;
  balance: string;
  due_date: string | null;
  status: StudentFeeStatus;
};

export type FinancialSummary = {
  student_id: string;
  total_due: string;
  total_paid: string;
  balance: string;
  fees: StudentFeeWithBalance[];
};

export type PaymentMethod = "CASH" | "BANK_TRANSFER" | "CHEQUE" | "AGENT_DEPOSIT" | "OTHER";
export type PaymentStatus = "COMPLETED" | "CANCELLED";

export type Payment = {
  id: string;
  amount: string;
  method: PaymentMethod;
  paid_at: string;
  status: PaymentStatus;
  receipt_number: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

export const children = {
  list: () => getJson<Child[]>("/api/v1/parent/children"),
};

export const childAttendance = {
  // Pas de sélecteur de période sur mobile (périmètre minimal) : agrégat toutes périodes.
  summary: (studentId: string) => getJson<AttendanceSummary>(`/api/v1/parent/children/${studentId}/attendance-summary`),
};

export const childGrades = {
  get: (studentId: string) => getJson<StudentAverages>(`/api/v1/parent/children/${studentId}/grades`),
};

export const childFees = {
  get: (studentId: string) => getJson<FinancialSummary>(`/api/v1/parent/children/${studentId}/fees`),
};

export const childPayments = {
  list: (studentId: string) => getJson<Payment[]>(`/api/v1/parent/children/${studentId}/payments`),
};

async function downloadReportCardPdf(studentId: string, reportCardId: string): Promise<string> {
  const path = `/api/v1/parent/children/${studentId}/report-cards/${reportCardId}/pdf`;
  const fileUri = `${FileSystem.cacheDirectory}bulletin-${reportCardId}.pdf`;

  const tokens = await getStoredTokens();
  if (!tokens) throw new ApiError("Session expirée — reconnectez-vous.", 401);

  // Transfert binaire natif (pas de fetch + conversion Blob/base64 côté JS) — mécanisme
  // d'authentification identique à apiFetch : même jeton, même stockage sécurisé (session.ts),
  // même endpoint protégé (le contrôle "mes enfants" + bulletin publié reste entièrement
  // côté serveur, cf. app/modules/parent/router.py — rien n'est contourné ici).
  let result = await FileSystem.downloadAsync(`${API_URL}${path}`, fileUri, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });

  if (result.status === 401) {
    // Même logique de rafraîchissement qu'apiFetch (fonction réutilisée, pas dupliquée).
    const refreshed = await refreshTokens();
    if (!refreshed) throw new ApiError("Session expirée — reconnectez-vous.", 401);
    const refreshedTokens = await getStoredTokens();
    result = await FileSystem.downloadAsync(`${API_URL}${path}`, fileUri, {
      headers: { Authorization: `Bearer ${refreshedTokens?.access_token}` },
    });
  }

  if (result.status === 404) throw new ApiError("Ce bulletin n'est plus disponible.", 404);
  if (result.status !== 200) throw new ApiError("Impossible de récupérer ce bulletin.", result.status);

  return fileUri;
}

export const childReportCards = {
  list: (studentId: string) => getJson<ReportCard[]>(`/api/v1/parent/children/${studentId}/report-cards`),

  /** Télécharge le PDF (authentifié) puis ouvre la feuille de partage/ouverture native. Pas de
   * lecteur PDF embarqué (hors périmètre) — on délègue à l'app que l'utilisateur choisit. */
  openPdf: async (studentId: string, reportCardId: string): Promise<void> => {
    if (Platform.OS === "web") {
      throw new ApiError("Le téléchargement de bulletin est disponible sur l'application mobile uniquement.", 0);
    }
    const fileUri = await downloadReportCardPdf(studentId, reportCardId);

    const canShare = await Sharing.isAvailableAsync();
    if (!canShare) throw new ApiError("Le partage de fichiers n'est pas disponible sur cet appareil.", 0);
    await Sharing.shareAsync(fileUri, { mimeType: "application/pdf", dialogTitle: "Bulletin" });
  },
};

async function downloadReceiptPdf(studentId: string, paymentId: string): Promise<string> {
  const path = `/api/v1/parent/children/${studentId}/payments/${paymentId}/receipt.pdf`;
  const fileUri = `${FileSystem.cacheDirectory}recu-${paymentId}.pdf`;

  const tokens = await getStoredTokens();
  if (!tokens) throw new ApiError("Session expirée — reconnectez-vous.", 401);

  let result = await FileSystem.downloadAsync(`${API_URL}${path}`, fileUri, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });

  if (result.status === 401) {
    const refreshed = await refreshTokens();
    if (!refreshed) throw new ApiError("Session expirée — reconnectez-vous.", 401);
    const refreshedTokens = await getStoredTokens();
    result = await FileSystem.downloadAsync(`${API_URL}${path}`, fileUri, {
      headers: { Authorization: `Bearer ${refreshedTokens?.access_token}` },
    });
  }

  if (result.status === 404) throw new ApiError("Ce reçu n'est plus disponible.", 404);
  if (result.status !== 200) throw new ApiError("Impossible de récupérer ce reçu.", result.status);

  return fileUri;
}

export const childReceipts = {
  /** Même motif que childReportCards.openPdf — pas de paiement/déclaration possible côté parent,
   * uniquement la consultation d'un reçu déjà émis (Phase 19 §21). */
  openPdf: async (studentId: string, paymentId: string): Promise<void> => {
    if (Platform.OS === "web") {
      throw new ApiError("Le téléchargement de reçu est disponible sur l'application mobile uniquement.", 0);
    }
    const fileUri = await downloadReceiptPdf(studentId, paymentId);

    const canShare = await Sharing.isAvailableAsync();
    if (!canShare) throw new ApiError("Le partage de fichiers n'est pas disponible sur cet appareil.", 0);
    await Sharing.shareAsync(fileUri, { mimeType: "application/pdf", dialogTitle: "Reçu" });
  },
};
