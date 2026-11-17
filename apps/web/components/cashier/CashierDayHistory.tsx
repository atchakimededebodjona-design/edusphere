"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { openReceipt } from "@/components/cashier/receipt";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { centsToApi, formatApiAmount, toCents } from "@/lib/fees/allocation";
import type { CashierDay } from "@/lib/fees/client";
import { PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";
import type { PaymentOutboxEntry } from "@/lib/offline/outbox";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** "Mes encaissements" — journal du jour de l'utilisateur connecté (`GET /cashier/payments`).
 *
 * Phase 32, lot 3 — en tête, les encaissements faits sans internet et pas encore enregistrés par le
 * serveur (`unsent`, gardés sur cet appareil), avec leur reçu provisoire à réimprimer. */
export function CashierDayHistory({
  day,
  error,
  onRetry,
  unsent = [],
  currency,
  onShowProvisional,
}: {
  day: CashierDay | null;
  error: string | null;
  onRetry: () => void;
  unsent?: PaymentOutboxEntry[];
  currency: string;
  onShowProvisional?: (entry: PaymentOutboxEntry) => void;
}) {
  const pendingCents = unsent
    .filter((entry) => entry.state === "pending")
    .reduce((sum, entry) => sum + (toCents(entry.payment.amount) ?? 0), 0);
  const [receiptError, setReceiptError] = useState<string | null>(null);

  async function handleReceipt(paymentId: string) {
    setReceiptError(null);
    try {
      await openReceipt(paymentId);
    } catch (err) {
      setReceiptError(toErrorMessage(err));
    }
  }

  return (
    <section aria-labelledby="cash-history-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="cash-history-title" className="text-lg font-semibold text-slate-900">
          Mes encaissements
        </h2>
        {day && (
          <p className="text-sm text-slate-600">
            {formatDateFR(day.day)} — Total encaissé :{" "}
            <span data-testid="cash-day-total" className="font-semibold text-slate-900">
              {formatApiAmount(day.total_completed, day.currency)}
            </span>
          </p>
        )}
      </div>

      {unsent.length > 0 && (
        <div className="flex flex-col gap-2">
          {pendingCents > 0 && (
            <p data-testid="cash-unsent-total" className="text-sm text-sky-900">
              En attente d&apos;envoi : <span className="font-semibold">{formatApiAmount(centsToApi(pendingCents), currency)}</span>
            </p>
          )}
          <ul
            aria-label="Encaissements gardés sur cet appareil"
            className="divide-y divide-sky-100 rounded border border-sky-300 bg-sky-50"
          >
            {unsent.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">
                    {entry.receipt.number}
                    <span className="ml-2 text-xs font-normal text-slate-500">{formatTime(entry.receipt.collectedAt)}</span>
                  </p>
                  <p className="truncate text-xs text-slate-600">
                    {entry.receipt.student.lastName} {entry.receipt.student.firstName} · {entry.receipt.student.matricule}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      entry.state === "failed" ? "bg-red-100 text-red-800" : "bg-sky-100 text-sky-900"
                    }`}
                  >
                    {entry.state === "failed" ? "Refusé" : "En attente d'envoi"}
                  </span>
                  <span className="font-semibold text-slate-900">{formatApiAmount(entry.payment.amount, currency)}</span>
                  {onShowProvisional && (
                    <button type="button" onClick={() => onShowProvisional(entry)} className="text-xs text-slate-700 underline">
                      Reçu provisoire
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <ErrorRetry message={error} onRetry={onRetry} />}
      {receiptError && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {receiptError}
        </p>
      )}
      {!day && !error && <p className="text-sm text-slate-500">Chargement...</p>}

      {day && day.payments.length === 0 && unsent.length === 0 && (
        <p className="text-sm text-slate-500">Aucun encaissement enregistré aujourd&apos;hui.</p>
      )}

      {day && day.payments.length > 0 && (
        <ul aria-label="Encaissements du jour" className="divide-y divide-slate-100 rounded border border-slate-200 bg-white">
          {day.payments.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">
                  {p.receipt_number}
                  <span className="ml-2 text-xs font-normal text-slate-500">{formatTime(p.created_at)}</span>
                </p>
                <p className="truncate text-xs text-slate-600">
                  {p.student_last_name} {p.student_first_name} · {p.student_matricule}
                </p>
                {p.provisional_receipt_number && (
                  <p className="text-xs text-amber-800">
                    Hors connexion · reçu provisoire {p.provisional_receipt_number}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-600">{PAYMENT_METHOD_LABELS[p.method]}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${
                    p.status === "CANCELLED" ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"
                  }`}
                >
                  {PAYMENT_STATUS_LABELS[p.status]}
                </span>
                <span className={`font-semibold ${p.status === "CANCELLED" ? "text-slate-400 line-through" : "text-slate-900"}`}>
                  {formatApiAmount(p.amount, day.currency)}
                </span>
                <button type="button" onClick={() => void handleReceipt(p.id)} className="text-xs text-slate-700 underline">
                  Reçu
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
