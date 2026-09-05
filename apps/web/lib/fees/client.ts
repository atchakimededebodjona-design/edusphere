import { apiFetch } from "@/lib/api/client";

export type FeeCategory = {
  id: string;
  school_id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type FeeCategoryCreate = { school_id: string; name: string };

export type FeeScopeType = "SCHOOL" | "CLASS" | "LEVEL";

export type FeeSchedule = {
  id: string;
  school_id: string;
  fee_category_id: string;
  academic_year_id: string;
  name: string;
  amount: string;
  currency: string;
  scope_type: FeeScopeType;
  scope_class_id: string | null;
  scope_education_level_id: string | null;
  is_optional: boolean;
  due_date: string | null;
  created_at: string;
  updated_at: string;
};

export type FeeScheduleCreate = {
  school_id: string;
  fee_category_id: string;
  academic_year_id: string;
  name: string;
  amount: string;
  scope_type: FeeScopeType;
  scope_class_id?: string | null;
  scope_education_level_id?: string | null;
  is_optional?: boolean;
  due_date?: string | null;
};

export type FeeScheduleGenerateResult = { created_count: number; skipped_existing_count: number };

export type StudentFeeStatus = "PENDING" | "PARTIALLY_PAID" | "PAID" | "CANCELLED";

export type StudentFeeWithBalance = {
  id: string;
  student_id: string;
  fee_schedule_id: string;
  fee_schedule_name: string;
  amount_due: string;
  amount_paid: string;
  balance: string;
  due_date: string | null;
  status: StudentFeeStatus;
  note: string | null;
  created_at: string;
  updated_at: string;
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
  student_id: string;
  amount: string;
  method: PaymentMethod;
  paid_at: string;
  reference: string | null;
  payer_name: string | null;
  note: string | null;
  status: PaymentStatus;
  receipt_number: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type PaymentCreate = {
  student_id: string;
  amount: string;
  method: PaymentMethod;
  paid_at: string;
  reference?: string | null;
  payer_name?: string | null;
  note?: string | null;
  idempotency_key: string;
  allocations: { student_fee_id: string; amount: string }[];
};

export type FeesSummary = { total_due: string; total_paid: string; balance: string; overdue_count: number };

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

export const feeCategories = {
  list: (schoolId: string) => getJson<FeeCategory[]>(`/api/v1/fee-categories?school_id=${schoolId}`),
  create: (payload: FeeCategoryCreate) => postJson<FeeCategory>("/api/v1/fee-categories", payload),
};

export const feeSchedules = {
  list: (schoolId: string, academicYearId?: string) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (academicYearId) params.set("academic_year_id", academicYearId);
    return getJson<FeeSchedule[]>(`/api/v1/fee-schedules?${params.toString()}`);
  },
  create: (payload: FeeScheduleCreate) => postJson<FeeSchedule>("/api/v1/fee-schedules", payload),
  generate: (id: string) => postJson<FeeScheduleGenerateResult>(`/api/v1/fee-schedules/${id}/generate`, {}),
};

export const studentFees = {
  update: (id: string, payload: { amount_due?: string; due_date?: string | null; note?: string | null }) =>
    patchJson<StudentFeeWithBalance>(`/api/v1/student-fees/${id}`, payload),
};

export const financialSummary = {
  get: (studentId: string) => getJson<FinancialSummary>(`/api/v1/students/${studentId}/financial-summary`),
};

export const payments = {
  list: (schoolId: string, filters: { studentId?: string; status?: PaymentStatus } = {}) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (filters.studentId) params.set("student_id", filters.studentId);
    if (filters.status) params.set("status", filters.status);
    return getJson<Payment[]>(`/api/v1/payments?${params.toString()}`);
  },
  create: (payload: PaymentCreate) => postJson<Payment>("/api/v1/payments", payload),
  cancel: (id: string, reason: string) => postJson<Payment>(`/api/v1/payments/${id}/cancel`, { reason }),
  getReceiptBlobUrl: async (id: string): Promise<string> => {
    const response = await apiFetch(`/api/v1/payments/${id}/receipt.pdf`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },
};

export const feesSummary = {
  get: (schoolId: string, academicYearId?: string) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (academicYearId) params.set("academic_year_id", academicYearId);
    return getJson<FeesSummary>(`/api/v1/fees/summary?${params.toString()}`);
  },
};
