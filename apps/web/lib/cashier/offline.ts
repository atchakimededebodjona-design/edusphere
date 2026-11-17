// Phase 32, lot 3 — encaisser pendant une coupure (voir docs/phases/PHASE_32_OFFLINE_PWA.md §5) :
// - recherche dans la liste des élèves gardée sur l'appareil (`GET /cashier/offline-roster`, copiée
//   comme toute lecture par lib/offline/responseCache.ts) ;
// - situation de l'élève reconstituée depuis la copie la plus récente (liste ou situation déjà
//   ouverte), diminuée des encaissements encore en attente d'envoi sur cet appareil ;
// - numéro de reçu provisoire.
// Rien ici n'est une autorité : chaque encaissement est revérifié par le serveur à son envoi.

import { getStoredUserId } from "@/lib/auth/session";
import { centsToApi, toCents } from "@/lib/fees/allocation";
import type {
  CashierRoster,
  CashierRosterStudent,
  CashierStudent,
  FinancialSummary,
  StudentFeeStatus,
  StudentFeeWithBalance,
} from "@/lib/fees/client";
import type { PaymentOutboxEntry } from "@/lib/offline/outbox";
import { readCachedResponse } from "@/lib/offline/responseCache";

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/** Même recherche que `GET /cashier/students/search` (matricule, prénom ou nom), sur la liste gardée. */
export function searchRoster(roster: CashierRoster, term: string, limit: number): CashierStudent[] {
  const needle = normalize(term);
  if (needle.length < 2) return [];
  return roster.students
    .filter((s) =>
      [s.matricule, s.first_name, s.last_name, `${s.last_name} ${s.first_name}`, `${s.first_name} ${s.last_name}`].some(
        (value) => normalize(value).includes(needle),
      ),
    )
    .slice(0, limit)
    .map((s) => ({
      id: s.id,
      matricule: s.matricule,
      first_name: s.first_name,
      last_name: s.last_name,
      current_class_name: s.current_class_name,
    }));
}

function cents(value: string): number {
  return toCents(value) ?? 0;
}

function withTotals(studentId: string, fees: StudentFeeWithBalance[]): FinancialSummary {
  const due = fees.reduce((sum, fee) => sum + cents(fee.amount_due), 0);
  const paid = fees.reduce((sum, fee) => sum + cents(fee.amount_paid), 0);
  return {
    student_id: studentId,
    total_due: centsToApi(due),
    total_paid: centsToApi(paid),
    balance: centsToApi(Math.max(due - paid, 0)),
    fees,
  };
}

/** Situation d'un élève telle que la liste gardée la décrit (même forme que la situation en ligne). */
export function rosterSummary(student: CashierRosterStudent): FinancialSummary {
  return withTotals(
    student.id,
    student.fees.map((fee) => ({
      id: fee.id,
      student_id: student.id,
      fee_schedule_id: "",
      fee_schedule_name: fee.fee_schedule_name,
      amount_due: fee.amount_due,
      amount_paid: fee.amount_paid,
      balance: fee.balance,
      due_date: fee.due_date,
      status: fee.status,
      note: null,
      created_at: fee.created_at,
      updated_at: fee.created_at,
    })),
  );
}

function feeStatus(paidCents: number, dueCents: number): StudentFeeStatus {
  if (paidCents <= 0) return "PENDING";
  return paidCents < dueCents ? "PARTIALLY_PAID" : "PAID";
}

/**
 * Retire de la situation les encaissements de cet élève encore EN ATTENTE sur l'appareil : le
 * serveur ne les connaît pas encore, deux encaissements hors connexion ne peuvent donc pas viser le
 * même reste à payer. Prudent par construction (au pire, un reste sous-estimé quelques secondes).
 */
export function withPendingPayments(summary: FinancialSummary, entries: PaymentOutboxEntry[]): FinancialSummary {
  const extra: Record<string, number> = {};
  for (const entry of entries) {
    if (entry.state !== "pending" || entry.studentId !== summary.student_id) continue;
    for (const allocation of entry.payment.allocations) {
      extra[allocation.student_fee_id] = (extra[allocation.student_fee_id] ?? 0) + cents(allocation.amount);
    }
  }
  if (Object.keys(extra).length === 0) return summary;
  const fees = summary.fees.map((fee) => {
    const added = extra[fee.id] ?? 0;
    if (added === 0 || fee.status === "CANCELLED") return fee;
    const due = cents(fee.amount_due);
    const paid = cents(fee.amount_paid) + added;
    return {
      ...fee,
      amount_paid: centsToApi(paid),
      balance: centsToApi(Math.max(due - paid, 0)),
      status: feeStatus(paid, due),
    };
  });
  return withTotals(summary.student_id, fees);
}

/**
 * Situation de l'élève sans internet : la copie la plus récente entre la liste gardée et la
 * situation déjà ouverte avec internet sur cet appareil. null si aucune des deux n'existe.
 */
export async function offlineSummary(studentId: string, roster: CashierRoster | null): Promise<FinancialSummary | null> {
  const fromRoster = roster?.students.find((s) => s.id === studentId) ?? null;
  const userId = getStoredUserId();
  const cached = userId ? await readCachedResponse(userId, `/api/v1/students/${studentId}/financial-summary`) : null;
  // Dates comparées comme instants (le serveur et l'appareil ne les écrivent pas au même format).
  if (cached && (!fromRoster || !roster || Date.parse(roster.generated_at) < Date.parse(cached.savedAt))) {
    try {
      return (await cached.response.json()) as FinancialSummary;
    } catch {
      // copie illisible : on se rabat sur la liste
    }
  }
  return fromRoster ? rosterSummary(fromRoster) : null;
}

/** Numéro du reçu provisoire remis au payeur : `PROV-` + 10 caractères hexadécimaux. */
export function newProvisionalReceiptNumber(): string {
  const bytes = new Uint8Array(5);
  crypto.getRandomValues(bytes);
  return `PROV-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}
