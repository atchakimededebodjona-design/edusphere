"use client";

import { useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { newProvisionalReceiptNumber } from "@/lib/cashier/offline";
import { formatDateFR } from "@/lib/format/date";
import {
  autoAllocate,
  centsToApi,
  centsToInput,
  checkAllocation,
  currencyLabel,
  formatApiAmount,
  formatMoney,
  localIsoDate,
  newIdempotencyKey,
  toAllocatableFees,
  toCents,
  totalBalanceCents,
} from "@/lib/fees/allocation";
import {
  payments,
  type CashierStudent,
  type FinancialSummary,
  type Payment,
  type PaymentCreate,
} from "@/lib/fees/client";
import { STUDENT_FEE_STATUS_LABELS } from "@/lib/fees/labels";
import { paymentKey, type ProvisionalReceipt } from "@/lib/offline/outbox";
import { saveNow } from "@/lib/offline/sync";

/** Phase 32, lot 3 — caisse ouverte connue : l'encaissement peut être gardé sur l'appareil si le
 * serveur ne répond pas (reçu provisoire), puis envoyé au retour d'internet. */
export type OfflineCollection = {
  schoolId: string;
  schoolName: string;
  cashSessionId: string;
  cashierName: string | null;
};

// Messages backend connus (fees/router.py, fees/service.py) traduits pour le comptoir ; tout autre
// message est affiché tel quel — le backend reste l'autorité, jamais contourné ici.
function paymentErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Erreur réseau : l'encaissement n'a pas pu être envoyé. Réessayez.";
  const detail = err.message;
  if (detail.includes("Cashiers can only record cash payments")) return "Un caissier ne peut enregistrer que des paiements en espèces.";
  if (detail.includes("exactly equal the payment amount")) return "Le total affecté doit être égal au montant reçu.";
  if (detail.includes("exceeds the remaining balance")) {
    return "Un montant affecté dépasse le solde restant (la situation a peut-être changé). Rechargez l'élève.";
  }
  if (detail.includes("An open cash session is required")) return "Aucune caisse ouverte : ouvrez votre caisse avant d'encaisser des espèces.";
  if (err.status === 403) return "Vous n'êtes pas autorisé à enregistrer ce paiement.";
  if (err.status === 429) return "Trop de tentatives d'encaissement. Patientez une minute puis réessayez.";
  return `L'encaissement a échoué : ${detail}`;
}

export function CashPaymentForm({
  student,
  summary,
  currency,
  onRecorded,
  offline = null,
  onQueued,
}: {
  student: CashierStudent;
  summary: FinancialSummary;
  currency: string;
  onRecorded: (payment: Payment) => void;
  offline?: OfflineCollection | null;
  /** `key` : cible de l'encaissement dans la boîte d'envoi (suivi de son envoi). */
  onQueued?: (receipt: ProvisionalReceipt, key: string) => void;
}) {
  const fees = useMemo(() => summary.fees.filter((fee) => fee.status !== "CANCELLED"), [summary]);
  const allocatable = useMemo(() => toAllocatableFees(fees), [fees]);
  const remainingTotal = totalBalanceCents(allocatable);

  const [amountInput, setAmountInput] = useState("");
  const [allocationInputs, setAllocationInputs] = useState<Record<string, string>>({});
  const [payerName, setPayerName] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [step, setStep] = useState<"form" | "confirm">("form");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Une clé par opération : créée au passage en confirmation, RÉUTILISÉE telle quelle si la même
  // opération est renvoyée (erreur réseau, double clic) — le backend renvoie alors le même paiement.
  const idempotencyKey = useRef<string | null>(null);
  // Lot 3 — numéro du reçu provisoire, lié à l'opération comme la clé d'idempotence.
  const provisionalNumber = useRef<string | null>(null);
  const submitting = useRef(false);

  const check = checkAllocation(allocatable, amountInput, allocationInputs);
  const allocationLines = fees
    .map((fee) => ({ fee, cents: toCents(allocationInputs[fee.id] ?? "") ?? 0 }))
    .filter((line) => line.cents > 0);

  function applyAllocation(cents: Record<string, number>) {
    setAllocationInputs(
      Object.fromEntries(Object.entries(cents).map(([id, value]) => [id, value > 0 ? centsToInput(value) : ""])),
    );
  }

  function editOperation() {
    // Toute modification de la saisie = nouvelle opération (nouvelle clé au prochain passage).
    idempotencyKey.current = null;
    provisionalNumber.current = null;
    setSubmitError(null);
  }

  function handleAutoAllocate() {
    if (check.amountCents === null || check.amountCents <= 0) return;
    editOperation();
    applyAllocation(autoAllocate(allocatable, check.amountCents));
  }

  function handlePayAll() {
    editOperation();
    setAmountInput(centsToInput(remainingTotal));
    applyAllocation(autoAllocate(allocatable, remainingTotal));
  }

  function goToConfirmation() {
    if (!check.canSubmit) return;
    idempotencyKey.current ??= newIdempotencyKey();
    setSubmitError(null);
    setStep("confirm");
  }

  async function confirmPayment() {
    if (submitting.current || !check.canSubmit || check.amountCents === null || !idempotencyKey.current) return;
    submitting.current = true;
    setIsSubmitting(true);
    setSubmitError(null);
    const body: PaymentCreate & { idempotency_key: string } = {
      student_id: student.id,
      amount: centsToApi(check.amountCents),
      method: "CASH",
      paid_at: localIsoDate(),
      payer_name: payerName.trim() || null,
      reference: reference.trim() || null,
      note: note.trim() || null,
      idempotency_key: idempotencyKey.current,
      allocations: allocationLines.map((line) => ({ student_fee_id: line.fee.id, amount: centsToApi(line.cents) })),
    };
    try {
      if (offline) await collectWithOfflineFallback(body, offline, check.amountCents);
      else onRecorded(await payments.create(body));
    } catch (err) {
      setSubmitError(paymentErrorMessage(err));
    } finally {
      submitting.current = false;
      setIsSubmitting(false);
    }
  }

  // Lot 3 — l'encaissement est d'abord gardé sur l'appareil, puis envoyé tout de suite : accepté, il
  // s'affiche comme avant ; serveur injoignable, il reste en attente et le reçu provisoire est remis.
  async function collectWithOfflineFallback(
    body: PaymentCreate & { idempotency_key: string },
    context: OfflineCollection,
    amountCents: number,
  ) {
    provisionalNumber.current ??= newProvisionalReceiptNumber();
    const number = provisionalNumber.current;
    const collectedAt = new Date().toISOString();
    const receipt: ProvisionalReceipt = {
      number,
      collectedAt,
      schoolName: context.schoolName,
      currency,
      student: {
        matricule: student.matricule,
        firstName: student.first_name,
        lastName: student.last_name,
        className: student.current_class_name,
      },
      amount: body.amount,
      allocations: allocationLines.map((line) => ({ name: line.fee.fee_schedule_name, amount: centsToApi(line.cents) })),
      payerName: body.payer_name ?? null,
      reference: body.reference ?? null,
      cashierName: context.cashierName,
    };
    const outcome = await saveNow({
      kind: "payment",
      key: paymentKey(body.idempotency_key),
      label: `Encaissement de ${formatMoney(amountCents, currency)} — ${student.last_name} ${student.first_name} (${number})`,
      schoolId: context.schoolId,
      studentId: student.id,
      payment: body,
      offline: { offline_collected_at: collectedAt, provisional_receipt_number: number, cash_session_id: context.cashSessionId },
      receipt,
    });
    if (outcome.status === "sent" && outcome.payment) onRecorded(outcome.payment);
    else if (outcome.status === "queued") onQueued?.(receipt, paymentKey(body.idempotency_key));
    else if (outcome.status === "rejected") setSubmitError(outcome.message);
    else {
      setSubmitError(
        "Encaissement NON enregistré : le serveur ne répond pas et cet appareil ne peut pas le garder (stockage indisponible). Ne remettez aucun reçu ; réessayez quand internet sera revenu.",
      );
    }
  }

  if (fees.length === 0 || remainingTotal === 0) {
    return (
      <section className="flex flex-col gap-3">
        <FeeSituation fees={fees} summary={summary} currency={currency} />
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {fees.length === 0 ? "Aucun frais à encaisser pour cet élève." : "Tous les frais de cet élève sont soldés."}
        </p>
      </section>
    );
  }

  if (step === "confirm" && check.amountCents !== null) {
    return (
      <section aria-labelledby="cash-confirm-title" className="flex flex-col gap-4 rounded-xl border border-slate-300 bg-white p-4">
        <h2 id="cash-confirm-title" className="text-lg font-semibold text-slate-900">
          Récapitulatif de l&apos;encaissement
        </h2>
        <dl className="grid gap-2 text-sm sm:grid-cols-[max-content_1fr] sm:gap-x-6">
          <dt className="text-slate-600">Élève</dt>
          <dd className="font-medium text-slate-900">
            {student.last_name} {student.first_name} ({student.matricule})
          </dd>
          <dt className="text-slate-600">Montant reçu</dt>
          <dd className="text-xl font-bold text-slate-900">{formatMoney(check.amountCents, currency)}</dd>
          <dt className="text-slate-600">Mode</dt>
          <dd className="font-medium text-slate-900">ESPÈCES</dd>
          {payerName.trim() && (
            <>
              <dt className="text-slate-600">Payeur</dt>
              <dd className="text-slate-900">{payerName.trim()}</dd>
            </>
          )}
        </dl>
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Détail des allocations</h3>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
            {allocationLines.map((line) => (
              <li key={line.fee.id} className="flex justify-between gap-3 px-3 py-2">
                <span>{line.fee.fee_schedule_name}</span>
                <span className="font-medium">{formatMoney(line.cents, currency)}</span>
              </li>
            ))}
            <li className="flex justify-between gap-3 bg-slate-50 px-3 py-2 font-semibold">
              <span>Total</span>
              <span>{formatMoney(check.allocatedCents, currency)}</span>
            </li>
          </ul>
        </div>
        {submitError && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {submitError}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={() => setStep("form")}
            disabled={isSubmitting}
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
          >
            Modifier
          </button>
          <button
            type="button"
            onClick={() => void confirmPayment()}
            disabled={isSubmitting}
            className="rounded-lg bg-emerald-700 px-6 py-3 text-base font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Enregistrement..." : "Confirmer l'encaissement"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <FeeSituation fees={fees} summary={summary} currency={currency} />

      <form
        aria-labelledby="cash-form-title"
        onSubmit={(e) => {
          e.preventDefault();
          goToConfirmation();
        }}
        className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4"
      >
        <h2 id="cash-form-title" className="text-lg font-semibold text-slate-900">
          Nouvel encaissement
        </h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-1 text-sm text-slate-700">
            Mode de paiement
            <input
              value="ESPÈCES"
              readOnly
              aria-readonly="true"
              className="min-h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-slate-100 px-3 font-semibold text-slate-900 sm:min-h-10"
            />
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-sm text-slate-700">
            Montant reçu{currency ? ` (${currencyLabel(currency)})` : ""}
            <input
              value={amountInput}
              onChange={(e) => {
                editOperation();
                setAmountInput(e.target.value);
              }}
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              aria-invalid={amountInput.trim() !== "" && (check.amountCents === null || check.amountCents <= 0)}
              className="w-full min-w-0 rounded-lg border border-slate-300 px-3 py-3 text-2xl font-bold tabular-nums text-slate-900 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleAutoAllocate}
            disabled={check.amountCents === null || check.amountCents <= 0}
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
          >
            Répartir automatiquement
          </button>
          <button
            type="button"
            onClick={handlePayAll}
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
          >
            Tout payer ({formatMoney(remainingTotal, currency)})
          </button>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-semibold text-slate-700">Répartition sur les frais</legend>
          <p className="text-xs text-slate-600">
            Le total affecté doit être exactement égal au montant reçu, sans dépasser le solde d&apos;un frais.
          </p>
          <ul className="grid gap-2 lg:grid-cols-2">
            {fees.map((fee) => {
              const balance = allocatable.find((a) => a.id === fee.id)?.balanceCents ?? 0;
              const exceeding = check.exceedingFeeIds.includes(fee.id);
              const invalid = check.invalidFeeIds.includes(fee.id);
              return (
                <li key={fee.id} className="flex flex-wrap items-end justify-between gap-2 rounded-lg border border-slate-200 p-3">
                  <div className="text-sm">
                    <p className="font-medium text-slate-900">{fee.fee_schedule_name}</p>
                    <p className="text-xs text-slate-600">Solde : {formatMoney(balance, currency)}</p>
                  </div>
                  <label className="flex flex-col gap-1 text-xs text-slate-600">
                    Montant affecté — {fee.fee_schedule_name}
                    <input
                      value={allocationInputs[fee.id] ?? ""}
                      onChange={(e) => {
                        editOperation();
                        setAllocationInputs((prev) => ({ ...prev, [fee.id]: e.target.value }));
                      }}
                      disabled={balance === 0}
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="0"
                      aria-invalid={exceeding || invalid}
                      className={`min-h-11 w-36 rounded-lg border px-2 text-right text-base tabular-nums focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 ${
                        exceeding || invalid ? "border-red-400 bg-red-50" : "border-slate-300"
                      } disabled:bg-slate-100`}
                    />
                    {exceeding && <span className="text-red-700">Dépasse le solde</span>}
                  </label>
                </li>
              );
            })}
          </ul>
        </fieldset>

        <details className="text-sm text-slate-700">
          <summary className="cursor-pointer select-none">Informations facultatives</summary>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Nom du payeur
              <input
                value={payerName}
                onChange={(e) => {
                  editOperation();
                  setPayerName(e.target.value);
                }}
                maxLength={255}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Référence
              <input
                value={reference}
                onChange={(e) => {
                  editOperation();
                  setReference(e.target.value);
                }}
                maxLength={255}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Note
              <input
                value={note}
                onChange={(e) => {
                  editOperation();
                  setNote(e.target.value);
                }}
                maxLength={2000}
                className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
              />
            </label>
          </div>
        </details>

        {/* Refonte, phase 2 (2026-11-23) : collée au-dessus de la barre du bas et des bandeaux (avant, elle
            passait dessous sur téléphone). */}
        <div
          className="sticky z-30 -mx-4 -mb-4 flex flex-col gap-3 rounded-b-xl border-t border-slate-200 bg-slate-50 p-4 shadow-[0_-4px_12px_-8px_rgba(15,23,42,0.25)] sm:flex-row sm:items-center sm:justify-between"
          style={{ bottom: "calc(var(--bottom-nav-height, 0px) + var(--bottom-banners-height, 0px))" }}
        >
          <dl aria-label="Totaux de l'encaissement" className="grid grid-cols-3 gap-3 text-xs sm:text-sm">
            <div>
              <dt className="text-slate-600">Total affecté</dt>
              <dd data-testid="cash-total-allocated" className="text-base font-bold text-slate-900 sm:text-lg">
                {formatMoney(check.allocatedCents, currency)}
              </dd>
            </div>
            <div>
              <dt className="text-slate-600">Montant reçu</dt>
              <dd data-testid="cash-amount-received" className="text-base font-bold text-slate-900 sm:text-lg">
                {formatMoney(check.amountCents ?? 0, currency)}
              </dd>
            </div>
            <div>
              <dt className="text-slate-600">Reste non affecté</dt>
              <dd
                data-testid="cash-unallocated"
                className={`text-base font-bold sm:text-lg ${check.unallocatedCents === 0 ? "text-slate-900" : "text-red-700"}`}
              >
                {formatMoney(check.unallocatedCents, currency)}
              </dd>
            </div>
          </dl>
          <div className="flex flex-col items-stretch gap-1 sm:items-end">
            <button
              type="submit"
              disabled={!check.canSubmit}
              className="inline-flex min-h-12 items-center justify-center rounded-lg bg-primary-600 px-6 text-base font-semibold text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Encaisser
            </button>
            {check.reason && amountInput.trim() !== "" && (
              <p className="text-xs text-red-700">{check.reason}</p>
            )}
          </div>
        </div>
      </form>
    </section>
  );
}

function FeeSituation({
  fees,
  summary,
  currency,
}: {
  fees: FinancialSummary["fees"];
  summary: FinancialSummary;
  currency: string;
}) {
  return (
    <section aria-labelledby="fee-situation-title" className="flex flex-col gap-2">
      <h2 id="fee-situation-title" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
        Situation des frais
      </h2>
      {fees.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {fees.map((fee) => (
            <li key={fee.id} data-testid="fee-situation-item" className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <p className="font-semibold text-slate-900">{fee.fee_schedule_name}</p>
                <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 font-semibold text-xs text-slate-700">
                  {STUDENT_FEE_STATUS_LABELS[fee.status]}
                </span>
              </div>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <dt className="text-slate-600">Dû</dt>
                  <dd className="font-medium text-slate-900">{formatApiAmount(fee.amount_due, currency)}</dd>
                </div>
                <div>
                  <dt className="text-slate-600">Payé</dt>
                  <dd className="font-medium text-slate-900">{formatApiAmount(fee.amount_paid, currency)}</dd>
                </div>
                <div>
                  <dt className="text-slate-600">Solde</dt>
                  <dd className="font-semibold text-slate-900">{formatApiAmount(fee.balance, currency)}</dd>
                </div>
              </dl>
              <p className="mt-1 text-xs text-slate-600">
                Échéance : {fee.due_date ? formatDateFR(fee.due_date) : "non définie"}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="text-base font-semibold text-slate-900">
        Total restant : <span data-testid="fee-total-remaining">{formatApiAmount(summary.balance, currency)}</span>
      </p>
    </section>
  );
}
