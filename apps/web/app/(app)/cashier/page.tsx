"use client";

import { useCallback, useEffect, useState } from "react";
import { CashierDayHistory } from "@/components/cashier/CashierDayHistory";
import { CashierStudentSearch } from "@/components/cashier/CashierStudentSearch";
import { CashPaymentForm } from "@/components/cashier/CashPaymentForm";
import { openReceipt } from "@/components/cashier/receipt";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount, localIsoDate } from "@/lib/fees/allocation";
import {
  cashier,
  financialSummary,
  type CashierDay,
  type CashierStudent,
  type FinancialSummary,
  type Payment,
} from "@/lib/fees/client";
import { formatDateFR } from "@/lib/format/date";

type Recorded = { payment: Payment; student: CashierStudent; newBalance: string | null };

// Caisse scolaire, lot 2 — poste d'encaissement en espèces. Affiché seulement avec
// `payments.manage` (lisibilité) ; l'API reste la seule autorité : CASH imposé au CAISSIER,
// isolation école/organisation, idempotence et plafonnement au solde sont tous vérifiés côté
// backend (fees/router.py, fees/service.py, cashier/router.py).
export default function CashierPage() {
  const { currentSchoolId, currentSchool, permissions, user } = useAuth();
  const canCollect = permissions.includes("payments.manage");

  const [day, setDay] = useState<CashierDay | null>(null);
  const [dayError, setDayError] = useState<string | null>(null);
  const [student, setStudent] = useState<CashierStudent | null>(null);
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<Recorded | null>(null);
  const [receiptError, setReceiptError] = useState<string | null>(null);

  const loadDay = useCallback(async (schoolId: string) => {
    setDayError(null);
    try {
      setDay(await cashier.myDay(schoolId, localIsoDate()));
    } catch (err) {
      setDayError(toErrorMessage(err));
    }
  }, []);

  const loadSummary = useCallback(async (studentId: string) => {
    setSummary(null);
    setSummaryError(null);
    try {
      setSummary(await financialSummary.get(studentId));
    } catch (err) {
      setSummaryError(toErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (canCollect && currentSchoolId) void loadDay(currentSchoolId);
  }, [canCollect, currentSchoolId, loadDay]);

  // Changement d'école : on repart d'un poste vierge (aucun élève d'une autre école conservé).
  useEffect(() => {
    setStudent(null);
    setSummary(null);
    setRecorded(null);
  }, [currentSchoolId]);

  function selectStudent(selected: CashierStudent) {
    setRecorded(null);
    setStudent(selected);
    void loadSummary(selected.id);
  }

  function resetDesk() {
    setRecorded(null);
    setStudent(null);
    setSummary(null);
    setSummaryError(null);
    setReceiptError(null);
  }

  async function handleRecorded(payment: Payment) {
    if (!student) return;
    setRecorded({ payment, student, newBalance: null });
    if (currentSchoolId) void loadDay(currentSchoolId);
    try {
      const refreshed = await financialSummary.get(student.id);
      setSummary(refreshed);
      setRecorded({ payment, student, newBalance: refreshed.balance });
    } catch {
      // Le paiement est enregistré (201) : un échec de relecture du solde n'annule rien, le
      // nouveau solde reste simplement non affiché (il figure aussi sur le reçu).
    }
  }

  async function handleReceipt(paymentId: string) {
    setReceiptError(null);
    try {
      await openReceipt(paymentId);
    } catch (err) {
      setReceiptError(toErrorMessage(err));
    }
  }

  if (!canCollect) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Caisse scolaire</h1>
        <p role="alert" className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          Cet espace est réservé aux comptes autorisés à enregistrer des paiements.
        </p>
      </div>
    );
  }

  if (!currentSchoolId) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  const currency = day?.currency ?? currentSchool?.currency ?? "";

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Caisse scolaire</h1>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {recorded ? (
            <section
              aria-labelledby="cash-success-title"
              className="flex flex-col gap-4 rounded border border-emerald-300 bg-emerald-50 p-4"
            >
              <h2 id="cash-success-title" className="text-xl font-bold text-emerald-900">
                Encaissement enregistré
              </h2>
              <dl className="grid gap-2 text-sm sm:grid-cols-[max-content_1fr] sm:gap-x-6">
                <dt className="text-emerald-800">Numéro de reçu</dt>
                <dd data-testid="cash-receipt-number" className="text-lg font-bold text-slate-900">
                  {recorded.payment.receipt_number}
                </dd>
                <dt className="text-emerald-800">Montant</dt>
                <dd className="text-lg font-bold text-slate-900">{formatApiAmount(recorded.payment.amount, currency)}</dd>
                <dt className="text-emerald-800">Élève</dt>
                <dd className="text-slate-900">
                  {recorded.student.last_name} {recorded.student.first_name} ({recorded.student.matricule})
                </dd>
                <dt className="text-emerald-800">Date</dt>
                <dd className="text-slate-900">{formatDateFR(recorded.payment.paid_at)}</dd>
                <dt className="text-emerald-800">Caissier</dt>
                <dd className="text-slate-900">{user?.full_name ?? "—"}</dd>
                <dt className="text-emerald-800">Nouveau solde</dt>
                <dd data-testid="cash-new-balance" className="font-semibold text-slate-900">
                  {recorded.newBalance === null ? "—" : formatApiAmount(recorded.newBalance, currency)}
                </dd>
              </dl>
              {receiptError && (
                <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {receiptError}
                </p>
              )}
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => void handleReceipt(recorded.payment.id)}
                  className="rounded border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-800 hover:bg-slate-100"
                >
                  Voir le reçu
                </button>
                <button
                  type="button"
                  onClick={resetDesk}
                  className="rounded bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-700"
                >
                  Nouvel encaissement
                </button>
              </div>
            </section>
          ) : student ? (
            <>
              <section
                aria-label="Élève sélectionné"
                className="flex flex-wrap items-center justify-between gap-3 rounded border border-slate-200 bg-white p-4"
              >
                <div>
                  <p data-testid="cash-selected-student" className="text-lg font-semibold text-slate-900">
                    {student.last_name} {student.first_name}
                  </p>
                  <p className="text-sm text-slate-600">
                    Matricule : {student.matricule} · Classe : {student.current_class_name ?? "non renseignée"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={resetDesk}
                  className="rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                >
                  Changer d&apos;élève
                </button>
              </section>
              {summaryError && <ErrorRetry message={summaryError} onRetry={() => void loadSummary(student.id)} />}
              {!summary && !summaryError && <p className="text-sm text-slate-500">Chargement de la situation...</p>}
              {summary && (
                <CashPaymentForm
                  key={student.id}
                  student={student}
                  summary={summary}
                  currency={currency}
                  onRecorded={(payment) => void handleRecorded(payment)}
                />
              )}
            </>
          ) : (
            <CashierStudentSearch schoolId={currentSchoolId} onSelect={selectStudent} />
          )}
        </div>

        <aside className="min-w-0">
          <CashierDayHistory day={day} error={dayError} onRetry={() => void loadDay(currentSchoolId)} />
        </aside>
      </div>
    </div>
  );
}
