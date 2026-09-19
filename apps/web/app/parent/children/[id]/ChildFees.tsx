"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import type { FinancialSummary, Payment } from "@/lib/fees/client";
import { parentChildren } from "@/lib/parent/client";

// Lecture seule uniquement (consigne Phase 28A) : aucun formulaire d'enregistrement de paiement
// ici, contrairement à app/(app)/students/[id]/StudentFinancialSummary.tsx côté admin — le
// backend `/parent/*` n'expose d'ailleurs aucun endpoint d'écriture pour ce module (voir
// parent/router.py, "le parent ne peut jamais créer, modifier, annuler un paiement").
export function ChildFees({ studentId }: { studentId: string }) {
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setSummary(null);
    setPayments(null);
    Promise.all([parentChildren.fees(studentId), parentChildren.payments(studentId)])
      .then(([s, p]) => {
        setSummary(s);
        setPayments(p);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDownloadReceipt(paymentId: string) {
    setDownloadError(null);
    try {
      const url = await parentChildren.getReceiptBlobUrl(studentId, paymentId);
      window.open(url, "_blank");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Le téléchargement a échoué.");
    }
  }

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (summary === null || payments === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-6 text-sm">
        <div>
          <p className="text-slate-500">Total dû</p>
          <p className="font-semibold text-slate-900">{summary.total_due}</p>
        </div>
        <div>
          <p className="text-slate-500">Total payé</p>
          <p className="font-semibold text-slate-900">{summary.total_paid}</p>
        </div>
        <div>
          <p className="text-slate-500">Solde</p>
          <p className="font-semibold text-slate-900">{summary.balance}</p>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Frais</h3>
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Frais</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Échéance</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Dû</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Payé</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Solde</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {summary.fees.map((fee) => (
                <tr key={fee.id}>
                  <td className="px-3 py-2">{fee.fee_schedule_name}</td>
                  <td className="px-3 py-2">{fee.due_date ?? "—"}</td>
                  <td className="px-3 py-2 text-right">{fee.amount_due}</td>
                  <td className="px-3 py-2 text-right">{fee.amount_paid}</td>
                  <td className="px-3 py-2 text-right">{fee.balance}</td>
                  <td className="px-3 py-2">{fee.status}</td>
                </tr>
              ))}
              {summary.fees.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                    Aucun frais affecté à cet élève.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Historique des paiements</h3>
        {downloadError && <p className="mb-2 text-sm text-red-700">{downloadError}</p>}
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Reçu</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Date</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Montant</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {payments.map((p) => (
                <tr key={p.id}>
                  <td className="px-3 py-2">{p.receipt_number}</td>
                  <td className="px-3 py-2">{p.paid_at}</td>
                  <td className="px-3 py-2 text-right">{p.amount}</td>
                  <td className="px-3 py-2">{p.status}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => void handleDownloadReceipt(p.id)}
                      className="text-xs text-slate-700 underline"
                    >
                      Reçu
                    </button>
                  </td>
                </tr>
              ))}
              {payments.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                    Aucun paiement enregistré.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
