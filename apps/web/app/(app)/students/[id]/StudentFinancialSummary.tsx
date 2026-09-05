"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  financialSummary,
  payments as paymentsClient,
  type FinancialSummary,
  type Payment,
  type PaymentMethod,
} from "@/lib/fees/client";

const METHOD_OPTIONS: { value: PaymentMethod; label: string }[] = [
  { value: "CASH", label: "Espèces" },
  { value: "BANK_TRANSFER", label: "Virement" },
  { value: "CHEQUE", label: "Chèque" },
  { value: "AGENT_DEPOSIT", label: "Dépôt agent" },
  { value: "OTHER", label: "Autre" },
];

export function StudentFinancialSummary({
  studentId,
  schoolId,
  canManage,
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
}) {
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [selectedFeeId, setSelectedFeeId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("CASH");
  const [paidAt, setPaidAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [payerName, setPayerName] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setSummary(await financialSummary.get(studentId));
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  async function handleRecordPayment(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedFeeId) return;
    setStatus("saving");
    setError(null);
    try {
      await paymentsClient.create({
        student_id: studentId,
        amount,
        method,
        paid_at: paidAt,
        reference: reference || null,
        payer_name: payerName || null,
        idempotency_key: idempotencyKey,
        allocations: [{ student_fee_id: selectedFeeId, amount }],
      });
      await reload();
      setAmount("");
      setReference("");
      setPayerName("");
      // Nouvelle clé pour le prochain paiement — celle-ci reste valable en cas de nouvelle
      // tentative après une erreur réseau sur CE paiement (protection double-soumission).
      setIdempotencyKey(crypto.randomUUID());
      setHistoryKey((k) => k + 1);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  async function handleDownloadReceipt(paymentId: string) {
    const url = await paymentsClient.getReceiptBlobUrl(paymentId);
    window.open(url, "_blank");
  }

  const [historyKey, setHistoryKey] = useState(0);

  async function handleCancel(paymentId: string) {
    const reason = window.prompt("Motif de l'annulation ?");
    if (!reason) return;
    await paymentsClient.cancel(paymentId, reason);
    await reload();
    setHistoryKey((k) => k + 1);
  }

  if (summary === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-slate-900">Situation financière</h2>

      <div className="flex gap-6 text-sm">
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

      {canManage && summary.fees.length > 0 && (
        <form onSubmit={handleRecordPayment} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Frais
            <select
              value={selectedFeeId}
              onChange={(e) => setSelectedFeeId(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {summary.fees
                .filter((f) => f.status !== "PAID" && f.status !== "CANCELLED")
                .map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.fee_schedule_name} (solde {f.balance})
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Montant
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Méthode
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              {METHOD_OPTIONS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Date
            <input
              type="date"
              value={paidAt}
              onChange={(e) => setPaidAt(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Référence
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Payeur
            <input
              value={payerName}
              onChange={(e) => setPayerName(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={status === "saving"} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {status === "saving" ? "Enregistrement..." : "Enregistrer le paiement"}
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <PaymentHistory
        studentId={studentId}
        schoolId={schoolId}
        canManage={canManage}
        refreshKey={historyKey}
        onDownload={handleDownloadReceipt}
        onCancel={handleCancel}
      />
    </div>
  );
}

function PaymentHistory({
  studentId,
  schoolId,
  canManage,
  refreshKey,
  onDownload,
  onCancel,
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
  refreshKey: number;
  onDownload: (paymentId: string) => void;
  onCancel: (paymentId: string) => void;
}) {
  const [items, setItems] = useState<Payment[] | null>(null);

  useEffect(() => {
    void paymentsClient.list(schoolId, { studentId }).then(setItems);
  }, [schoolId, studentId, refreshKey]);

  if (items === null) return <p className="text-sm text-slate-400">Chargement de l&apos;historique...</p>;

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-slate-900">Historique des paiements</h3>
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
                    <button type="button" onClick={() => onDownload(p.id)} className="text-xs text-slate-700 underline">
                      Reçu
                    </button>
                    {canManage && p.status === "COMPLETED" && (
                      <button type="button" onClick={() => onCancel(p.id)} className="text-xs text-red-700 underline">
                        Annuler
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                  Aucun paiement enregistré.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
