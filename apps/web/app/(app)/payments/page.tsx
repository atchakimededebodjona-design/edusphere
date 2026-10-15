"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { cancelPaymentErrorMessage } from "@/lib/fees/cancelErrors";
import { feesSummary, payments as paymentsClient, type FeesSummary, type Payment, type PaymentStatus } from "@/lib/fees/client";

export default function PaymentsPage() {
  const { currentSchoolId, permissions } = useAuth();
  // Même permission que celle exigée par POST /payments/{id}/cancel (lot 1 : `payments.cancel`,
  // distincte de `payments.manage` qui ne couvre que l'enregistrement). Affichage seulement : l'API
  // reste l'autorité.
  const canCancel = permissions.includes("payments.cancel");
  const [items, setItems] = useState<Payment[] | null>(null);
  const [summary, setSummary] = useState<FeesSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState<PaymentStatus | "">("");
  const [loadError, setLoadError] = useState<string | null>(null);
  // Annulation : un seul envoi par paiement à la fois (double clic, clics concurrents), bouton
  // désactivé pendant la requête, erreur affichée sans jamais présenter l'annulation comme faite.
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<{ receipt: string; message: string } | null>(null);
  const cancelInFlight = useRef<Set<string>>(new Set());

  async function reload(schoolId: string) {
    setLoadError(null);
    try {
      const [list, agg] = await Promise.all([
        paymentsClient.list(schoolId, statusFilter ? { status: statusFilter } : {}),
        feesSummary.get(schoolId),
      ]);
      setItems(list);
      setSummary(agg);
    } catch (err) {
      setLoadError(toErrorMessage(err));
    }
  }

  useEffect(() => {
    if (currentSchoolId) void reload(currentSchoolId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSchoolId, statusFilter]);

  async function handleDownload(paymentId: string) {
    const url = await paymentsClient.getReceiptBlobUrl(paymentId);
    window.open(url, "_blank");
  }

  async function handleCancel(payment: Payment) {
    if (!currentSchoolId || cancelInFlight.current.has(payment.id)) return;
    cancelInFlight.current.add(payment.id);
    try {
      const reason = window.prompt("Motif de l'annulation ?");
      if (!reason) return;
      setCancelError(null);
      setCancellingId(payment.id);
      try {
        await paymentsClient.cancel(payment.id, reason);
      } catch (err) {
        // Refus (409 session clôturée, 403...) ou réseau : rien n'est rechargé ni modifié localement,
        // le paiement reste affiché tel quel (le backend n'a rien changé).
        setCancelError({ receipt: payment.receipt_number, message: cancelPaymentErrorMessage(err) });
        return;
      }
      await reload(currentSchoolId); // succès : comportement existant (liste et totaux relus)
    } finally {
      cancelInFlight.current.delete(payment.id);
      setCancellingId((current) => (current === payment.id ? null : current));
    }
  }

  if (loadError) {
    return <ErrorRetry message={loadError} onRetry={() => currentSchoolId && void reload(currentSchoolId)} />;
  }

  if (!currentSchoolId || items === null || summary === null) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Paiements</h1>

      {cancelError && (
        <div
          role="alert"
          data-testid="payment-cancel-error"
          className="flex flex-wrap items-center justify-between gap-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          <span>
            Reçu {cancelError.receipt} — {cancelError.message}
          </span>
          <button
            type="button"
            onClick={() => setCancelError(null)}
            className="shrink-0 rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
          >
            Fermer
          </button>
        </div>
      )}

      <div className="flex gap-6 rounded border border-slate-200 bg-slate-50 p-4 text-sm">
        <div>
          <p className="text-slate-500">Total facturé</p>
          <p className="font-semibold text-slate-900">{summary.total_due}</p>
        </div>
        <div>
          <p className="text-slate-500">Total encaissé</p>
          <p className="font-semibold text-slate-900">{summary.total_paid}</p>
        </div>
        <div>
          <p className="text-slate-500">Solde global</p>
          <p className="font-semibold text-slate-900">{summary.balance}</p>
        </div>
        <div>
          <p className="text-slate-500">Échéances dépassées</p>
          <p className="font-semibold text-slate-900">{summary.overdue_count}</p>
        </div>
      </div>

      <label className="flex w-fit flex-col gap-1 text-xs text-slate-600">
        Statut
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as PaymentStatus | "")}
          className="rounded border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="">Tous</option>
          <option value="COMPLETED">Complétés</option>
          <option value="CANCELLED">Annulés</option>
        </select>
      </label>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Reçu</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Date</th>
              <th className="px-3 py-2 text-right font-medium text-slate-600">Montant</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Méthode</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((p) => (
              <tr key={p.id}>
                <td className="px-3 py-2">{p.receipt_number}</td>
                <td className="px-3 py-2">{p.paid_at}</td>
                <td className="px-3 py-2 text-right">{p.amount}</td>
                <td className="px-3 py-2">{p.method}</td>
                <td className="px-3 py-2">{p.status}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => void handleDownload(p.id)} className="text-xs text-slate-700 underline">
                      Reçu
                    </button>
                    {canCancel && p.status === "COMPLETED" && (
                      <button
                        type="button"
                        onClick={() => void handleCancel(p)}
                        disabled={cancellingId === p.id}
                        aria-busy={cancellingId === p.id}
                        className="text-xs text-red-700 underline disabled:cursor-wait disabled:opacity-50"
                      >
                        {cancellingId === p.id ? "Annulation..." : "Annuler"}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                  Aucun paiement.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
