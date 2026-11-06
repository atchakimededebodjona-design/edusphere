import { expect, type APIRequestContext } from "@playwright/test";
import { API_BASE_URL, TENANT_PASSWORD, createOrganizationViaPlatform, unique, type TenantAdmin } from "./tenants";

// Mise en place partagée des specs caisse (cashier.spec.ts — lot 2, cash-register.spec.ts — lot 3) :
// préparation par l'API réelle uniquement, jamais par la base directement.

export type Desk = {
  tenant: TenantAdmin;
  studentLastName: string;
  studentFirstName: string;
  matricule: string;
  cashierEmail: string;
  cashierToken: string;
};

export async function api(request: APIRequestContext, token: string, method: "GET" | "POST", path: string, data?: unknown) {
  const response = await request.fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

export async function createUser(request: APIRequestContext, tenant: TenantAdmin, roleCode: string, fullName: string): Promise<string> {
  const email = `${unique(roleCode.toLowerCase()).toLowerCase()}@wizard-e2e.example`;
  const created = await api(request, tenant.orgAdminToken, "POST", "/api/v1/users", {
    email,
    full_name: fullName,
    school_id: tenant.schoolId,
    role_code: roleCode,
  });
  const reset = await request.post(`${API_BASE_URL}/api/v1/auth/reset-password`, {
    data: { token: created.dev_reset_token, new_password: TENANT_PASSWORD },
  });
  expect(reset.status()).toBe(204);
  return email;
}

export async function apiToken(request: APIRequestContext, email: string): Promise<string> {
  const login = await request.post(`${API_BASE_URL}/api/v1/auth/login`, { data: { email, password: TENANT_PASSWORD } });
  expect(login.ok()).toBeTruthy();
  return (await login.json()).access_token;
}

/** Élève avec deux frais — Scolarité 150 000 (échéance proche, 50 000 déjà payés) et Cantine 30 000
 * (échéance plus lointaine, 10 000 déjà payés) : total restant 120 000 FCFA, comme l'exemple métier.
 * `openSession` (lot 3) : ouvre la caisse du CAISSIER via l'API (fonds initial 0). */
export async function setupDesk(
  request: APIRequestContext,
  prefix: string,
  { openSession = true }: { openSession?: boolean } = {},
): Promise<Desk> {
  const tenant = await createOrganizationViaPlatform(request, prefix);
  const token = tenant.orgAdminToken;
  const schoolId = tenant.schoolId;
  const year = await api(request, token, "POST", "/api/v1/academic-years", {
    school_id: schoolId,
    name: `${prefix}-2026`,
    start_date: "2026-09-01",
    end_date: "2027-06-30",
  });
  const level = await api(request, token, "POST", "/api/v1/education-levels", { school_id: schoolId, name: "CM1" });
  const schoolClass = await api(request, token, "POST", "/api/v1/classes", {
    academic_year_id: year.id,
    education_level_id: level.id,
    name: "CM1 A",
  });
  const matricule = unique("CAISSE").toUpperCase();
  const studentLastName = `Mensah${unique("").slice(-5)}`;
  const studentFirstName = "Ama";
  const student = await api(request, token, "POST", "/api/v1/students", {
    school_id: schoolId,
    matricule,
    first_name: studentFirstName,
    last_name: studentLastName,
    date_of_birth: "2015-01-01",
    sex: "F",
  });
  await api(request, token, "POST", `/api/v1/students/${student.id}/enrollments`, {
    class_id: schoolClass.id,
    enrollment_date: "2026-09-01",
  });

  const feeIds: Record<string, string> = {};
  for (const [name, amount, dueDate] of [
    ["Scolarité", "150000", "2026-10-15"],
    ["Cantine", "30000", "2026-12-15"],
  ] as const) {
    const category = await api(request, token, "POST", "/api/v1/fee-categories", { school_id: schoolId, name });
    const schedule = await api(request, token, "POST", "/api/v1/fee-schedules", {
      school_id: schoolId,
      fee_category_id: category.id,
      academic_year_id: year.id,
      name,
      amount,
      scope_type: "SCHOOL",
      due_date: dueDate,
    });
    await api(request, token, "POST", `/api/v1/fee-schedules/${schedule.id}/generate`);
  }
  const summary = await api(request, token, "GET", `/api/v1/students/${student.id}/financial-summary`);
  for (const fee of summary.fees) feeIds[fee.fee_schedule_name] = fee.id;
  await api(request, token, "POST", "/api/v1/payments", {
    student_id: student.id,
    amount: "60000",
    method: "CASH",
    paid_at: "2026-10-01",
    idempotency_key: unique("seedpay"),
    allocations: [
      { student_fee_id: feeIds["Scolarité"], amount: "50000" },
      { student_fee_id: feeIds["Cantine"], amount: "10000" },
    ],
  });

  const cashierEmail = await createUser(request, tenant, "CAISSIER", "Kodjo Caissier");
  const cashierToken = await apiToken(request, cashierEmail);
  if (openSession) {
    await api(request, cashierToken, "POST", "/api/v1/cash/sessions/open", { school_id: schoolId, opening_amount: "0" });
  }
  return { tenant, studentLastName, studentFirstName, matricule, cashierEmail, cashierToken };
}
