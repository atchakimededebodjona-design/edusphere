"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { openReceipt } from "@/components/cashier/receipt";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { formatApiAmount } from "@/lib/fees/allocation";
import type { CashierDay } from "@/lib/fees/client";
import { PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** "Mes encaissements" — journal du jour de l'utilisateur connecté (`GET /cashier/payments`). */
export function CashierDayHistory({
  day,
  error,
  onRetry,
}: {
  day: CashierDay | null;
  error: string | null;
  onRetry: () => void;
}) {
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

      {error && <ErrorRetry message={error} onRetry={onRetry} />}
      {receiptError && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {receiptError}
        </p>
      )}
      {!day && !error && <p className="text-sm text-slate-500">Chargement...</p>}

      {day && day.payments.length === 0 && (
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
