// Caisse scolaire, lot 3 — sessions de caisse (api: modules/cash). Types alignés sur
// apps/api/app/modules/cash/schemas.py ; montants = chaînes décimales de l'API (jamais de flottant).
import { apiFetch } from "@/lib/api/client";
import type { PaymentMethod, PaymentStatus } from "@/lib/fees/client";

export type CashSessionStatus = "OPEN" | "CLOSED";
export type CashMovementType = "CASH_IN" | "CASH_OUT" | "BANK_DEPOSIT" | "OTHER";
export type CashMovementDirection = "IN" | "OUT";
export type CashVarianceReason =
  | "COUNTING_ERROR"
  | "CHANGE_ERROR"
  | "UNRECORDED_PAYMENT"
  | "UNRECORDED_MOVEMENT"
  | "LOSS_OR_THEFT"
  | "OTHER";

export type CashSession = {
  id: string;
  school_id: string;
  cashier_user_id: string;
  cashier_name: string | null;
  opened_at: string;
  opened_by: string;
  opening_amount: string;
  status: CashSessionStatus;
  closed_at: string | null;
  closed_by: string | null;
  expected_amount: string | null;
  counted_amount: string | null;
  variance_amount: string | null;
  variance_reason: CashVarianceReason | null;
  variance_note: string | null;
  business_date: string;
};

export type CashTotals = {
  opening_amount: string;
  cash_payments_total: string;
  cash_payments_count: number;
  movements_in_total: string;
  movements_out_total: string;
  expected_amount: string;
};

export type CashMovement = {
  id: string;
  cash_session_id: string;
  type: CashMovementType;
  direction: CashMovementDirection;
  amount: string;
  reason: string;
  reference: string | null;
  created_by: string;
  created_at: string;
};

export type CashCountLine = { denomination: string; quantity: number; line_total: string };

export type CashCount = {
  id: string;
  cash_session_id: string;
  counted_by: string;
  counted_at: string;
  total_amount: string;
  lines: CashCountLine[];
};

export type CashSessionPayment = {
  id: string;
  receipt_number: string;
  amount: string;
  method: PaymentMethod;
  status: PaymentStatus;
  paid_at: string;
  created_at: string;
  student_id: string;
  student_matricule: string;
  student_first_name: string;
  student_last_name: string;
};

export type CashSessionDetail = {
  session: CashSession;
  totals: CashTotals;
  payments: CashSessionPayment[];
  movements: CashMovement[];
  latest_count: CashCount | null;
  currency: string;
};

export type CashRegisterContext = {
  school_id: string;
  currency: string;
  timezone: string;
  business_date: string;
  denominations: string[];
  variance_reasons: CashVarianceReason[];
  current: CashSessionDetail | null;
};

export type CashSessionSummary = CashSession & {
  cash_payments_total: string;
  cash_payments_count: number;
  movements_in_total: string;
  movements_out_total: string;
  current_expected_amount: string;
};

export type CashMovementCreate = {
  type: CashMovementType;
  direction?: CashMovementDirection | null;
  amount: string;
  reason: string;
  reference?: string | null;
  idempotency_key: string;
};

export type CashSessionClose = {
  count_id: string;
  expected_amount: string;
  variance_reason?: CashVarianceReason | null;
  variance_note?: string | null;
};

export type CashSessionsAggregate = {
  sessions_count: number;
  open_count: number;
  closed_count: number;
  opening_total: string;
  cash_payments_total: string;
  movements_in_total: string;
  movements_out_total: string;
  expected_total: string;
  counted_total: string;
  variance_total: string;
};

export type PaymentMethodTotal = {
  method: PaymentMethod;
  completed_count: number;
  completed_total: string;
  cancelled_count: number;
  cancelled_total: string;
};

export type CashDailyReport = {
  day: string;
  currency: string;
  timezone: string;
  sessions: CashSessionsAggregate;
  payments_by_method: PaymentMethodTotal[];
};

export type CashierReportRow = {
  cashier_user_id: string;
  cashier_name: string | null;
  sessions_count: number;
  open_count: number;
  cash_payments_total: string;
  cash_payments_count: number;
  movements_in_total: string;
  movements_out_total: string;
  variance_total: string;
};

export type CashierReport = { date_from: string; date_to: string; currency: string; rows: CashierReportRow[] };
export type PaymentMethodReport = { date_from: string; date_to: string; currency: string; rows: PaymentMethodTotal[] };

export type SessionListFilters = {
  status?: CashSessionStatus;
  dateFrom?: string;
  dateTo?: string;
  cashierUserId?: string;
};

async function getJson<T>(path: string): Promise<T> {
  return (await apiFetch(path)).json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

function rangeParams(schoolId: string, dateFrom?: string, dateTo?: string): URLSearchParams {
  const params = new URLSearchParams({ school_id: schoolId });
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return params;
}

export const cashRegister = {
  current: (schoolId: string) =>
    getJson<CashRegisterContext>(`/api/v1/cash/sessions/current?${new URLSearchParams({ school_id: schoolId })}`),
  open: (schoolId: string, openingAmount: string) =>
    postJson<CashSessionDetail>("/api/v1/cash/sessions/open", { school_id: schoolId, opening_amount: openingAmount }),
  get: (sessionId: string) => getJson<CashSessionDetail>(`/api/v1/cash/sessions/${sessionId}`),
  addMovement: (sessionId: string, payload: CashMovementCreate) =>
    postJson<CashMovement>(`/api/v1/cash/sessions/${sessionId}/movements`, payload),
  count: (sessionId: string, lines: { denomination: string; quantity: number }[]) =>
    postJson<CashCount>(`/api/v1/cash/sessions/${sessionId}/count`, { lines }),
  close: (sessionId: string, payload: CashSessionClose) =>
    postJson<CashSessionDetail>(`/api/v1/cash/sessions/${sessionId}/close`, payload),
  list: (schoolId: string, filters: SessionListFilters = {}) => {
    const params = rangeParams(schoolId, filters.dateFrom, filters.dateTo);
    if (filters.status) params.set("status", filters.status);
    if (filters.cashierUserId) params.set("cashier_user_id", filters.cashierUserId);
    return getJson<CashSessionSummary[]>(`/api/v1/cash/sessions?${params}`);
  },
};

export const cashReports = {
  daily: (schoolId: string, day?: string) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (day) params.set("day", day);
    return getJson<CashDailyReport>(`/api/v1/cash/reports/daily?${params}`);
  },
  cashiers: (schoolId: string, dateFrom?: string, dateTo?: string) =>
    getJson<CashierReport>(`/api/v1/cash/reports/cashiers?${rangeParams(schoolId, dateFrom, dateTo)}`),
  methods: (schoolId: string, dateFrom?: string, dateTo?: string) =>
    getJson<PaymentMethodReport>(`/api/v1/cash/reports/methods?${rangeParams(schoolId, dateFrom, dateTo)}`),
  // Nom de fichier construit ici (même format que l'API) : l'en-tête Content-Disposition n'est pas
  // lisible en cross-origin (non exposé par CORS), inutile d'élargir la configuration CORS pour ça.
  downloadCsv: async (schoolId: string, dateFrom: string, dateTo: string): Promise<{ url: string; filename: string }> => {
    const response = await apiFetch(`/api/v1/cash/reports/export.csv?${rangeParams(schoolId, dateFrom, dateTo)}`);
    return { url: URL.createObjectURL(await response.blob()), filename: `caisse_${dateFrom}_${dateTo}.csv` };
  },
};
