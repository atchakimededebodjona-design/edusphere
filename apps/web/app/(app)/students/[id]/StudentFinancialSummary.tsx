"use client";

import { useCallback, useEffect, useState } from "react";
import { openReceipt } from "@/components/cashier/receipt";
import { Button } from "@/components/ui/Button";
import { DataTable, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { Modal } from "@/components/ui/Dialog";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { SelectField, TextField } from "@/components/ui/Field";
import { Alert, Badge, EmptyState, StatCard, type Tone } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import {
  financialSummary,
  payments as paymentsClient,
  type FinancialSummary,
  type Payment,
  type PaymentMethod,
  type StudentFeeStatus,
  type StudentFeeWithBalance,
} from "@/lib/fees/client";
import { PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS, STUDENT_FEE_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";

const METHOD_OPTIONS: { value: PaymentMethod; label: string }[] = [
  { value: "CASH", label: "Espèces" },
  { value: "BANK_TRANSFER", label: "Virement" },
  { value: "CHEQUE", label: "Chèque" },
  { value: "AGENT_DEPOSIT", label: "Dépôt agent" },
  { value: "OTHER", label: "Autre" },
];

const FEE_TONES: Record<StudentFeeStatus, Tone> = {
  PENDING: "warning",
  PARTIALLY_PAID: "info",
  PAID: "success",
  CANCELLED: "neutral",
};

// Refonte, phase 3 lot B (2026-11-24) — montants en francs, dates et statuts en français, tableaux en
// cartes sur téléphone, motif d'annulation dans une fenêtre de l'application (plus de window.prompt).
// Mêmes appels à l'API qu'avant.
export function StudentFinancialSummary({
  studentId,
  schoolId,
  canManage,
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
}) {
  const { currentSchool } = useAuth();
  const currency = currentSchool?.currency ?? "";
  const money = (amount: string) => formatApiAmount(amount, currency);
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Payment | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const reload = useCallback(async () => {
    setLoadError(null);
    try {
      setSummary(await financialSummary.get(studentId));
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }, [studentId]);

  useEffect(() => {
    void reload();
  }, [reload]);

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
    setActionError(null);
    try {
      await openReceipt(paymentId);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }

  const [historyKey, setHistoryKey] = useState(0);

  async function handleCancel(payment: Payment, reason: string) {
    if (!reason || cancelling) return;
    setCancelling(true);
    setActionError(null);
    try {
      await paymentsClient.cancel(payment.id, reason);
      setCancelTarget(null);
      await reload();
      setHistoryKey((k) => k + 1);
    } catch (err) {
      // Avant, un refus de l'API passait inaperçu (promesse non gérée) : il est maintenant affiché.
      setCancelTarget(null);
      setActionError(`Reçu ${payment.receipt_number} — ${err instanceof ApiError ? err.message : "Une erreur est survenue."}`);
    } finally {
      setCancelling(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={() => void reload()} />;
  if (summary === null) return <TableSkeleton rows={3} />;

  const feeColumns: Column<StudentFeeWithBalance>[] = [
    { key: "name", header: "Frais", mobile: "title", cell: (fee) => fee.fee_schedule_name },
    { key: "due", header: "Échéance", cell: (fee) => (fee.due_date ? formatDateFR(fee.due_date) : "—") },
    { key: "status", header: "Statut", cell: (fee) => <Badge tone={FEE_TONES[fee.status]}>{STUDENT_FEE_STATUS_LABELS[fee.status] ?? fee.status}</Badge> },
    { key: "amount_due", header: "Dû", align: "right", cell: (fee) => money(fee.amount_due) },
    { key: "amount_paid", header: "Payé", align: "right", cell: (fee) => money(fee.amount_paid) },
    { key: "balance", header: "Solde", align: "right", cell: (fee) => <span className="font-semibold text-slate-900">{money(fee.balance)}</span> },
  ];

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <h2 className="text-lg font-bold text-slate-900">Situation financière</h2>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Total dû" value={money(summary.total_due)} />
        <StatCard label="Total payé" tone="success" value={money(summary.total_paid)} />
        <StatCard label="Solde" tone="warning" value={money(summary.balance)} />
      </div>

      <DataTable
        caption="Frais de l'élève"
        columns={feeColumns}
        rows={summary.fees}
        rowKey={(fee) => fee.id}
        rowTone={(fee) => (fee.status === "CANCELLED" ? "muted" : undefined)}
        empty={<EmptyState icon="wallet" title="Aucun frais affecté à cet élève." />}
      />

      {canManage && summary.fees.length > 0 && (
        <form onSubmit={handleRecordPayment} className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
          <p className="text-base font-bold text-slate-900">Enregistrer un paiement</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SelectField label="Frais" value={selectedFeeId} onChange={(e) => setSelectedFeeId(e.target.value)} required>
              <option value="">—</option>
              {summary.fees
                .filter((f) => f.status !== "PAID" && f.status !== "CANCELLED")
                .map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.fee_schedule_name} (solde {money(f.balance)})
                  </option>
                ))}
            </SelectField>
            <TextField
              label="Montant"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
            <SelectField label="Méthode" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
              {METHOD_OPTIONS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </SelectField>
            <TextField label="Date" type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} required />
            <TextField label="Référence" value={reference} onChange={(e) => setReference(e.target.value)} hint="Facultatif" />
            <TextField label="Payeur" value={payerName} onChange={(e) => setPayerName(e.target.value)} hint="Facultatif" />
          </div>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" disabled={status === "saving"} className="self-start">
            {status === "saving" ? "Enregistrement..." : "Enregistrer le paiement"}
          </Button>
        </form>
      )}

      {actionError && <Alert tone="danger">{actionError}</Alert>}

      <PaymentHistory
        studentId={studentId}
        schoolId={schoolId}
        canManage={canManage}
        refreshKey={historyKey}
        money={money}
        onDownload={(id) => void handleDownloadReceipt(id)}
        onCancel={(payment) => {
          setCancelReason("");
          setCancelTarget(payment);
        }}
      />

      <Modal open={cancelTarget !== null} onClose={() => setCancelTarget(null)} title="Annuler le paiement">
        {cancelTarget && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void handleCancel(cancelTarget, cancelReason.trim());
            }}
          >
            <p className="text-sm text-slate-700">
              Reçu <strong>{cancelTarget.receipt_number}</strong>, {money(cancelTarget.amount)}. Le paiement restera dans
              l&apos;historique, marqué « Annulé », et le solde des frais sera recalculé.
            </p>
            <TextField
              label="Motif de l'annulation"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              required
              data-autofocus
              hint="Obligatoire. Il reste affiché sur le paiement annulé."
            />
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="secondary" onClick={() => setCancelTarget(null)} disabled={cancelling}>
                Retour
              </Button>
              <Button type="submit" variant="danger" disabled={cancelReason.trim() === "" || cancelling}>
                {cancelling ? "Annulation..." : "Confirmer l'annulation"}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </section>
  );
}

function PaymentHistory({
  studentId,
  schoolId,
  canManage,
  refreshKey,
  money,
  onDownload,
  onCancel,
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
  refreshKey: number;
  money: (amount: string) => string;
  onDownload: (paymentId: string) => void;
  onCancel: (payment: Payment) => void;
}) {
  const [items, setItems] = useState<Payment[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadHistory = useCallback(() => {
    setLoadError(null);
    paymentsClient
      .list(schoolId, { studentId })
      .then(setItems)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId, studentId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory, refreshKey]);

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadHistory} />;
  if (items === null) return <TableSkeleton rows={2} />;

  const columns: Column<Payment>[] = [
    { key: "receipt", header: "Reçu", mobile: "title", cell: (p) => p.receipt_number },
    { key: "date", header: "Date", cell: (p) => formatDateFR(p.paid_at) },
    {
      key: "amount",
      header: "Montant",
      align: "right",
      cell: (p) => <span className={`font-semibold ${p.status === "CANCELLED" ? "text-slate-600 line-through" : "text-slate-900"}`}>{money(p.amount)}</span>,
    },
    { key: "method", header: "Mode", cell: (p) => PAYMENT_METHOD_LABELS[p.method] ?? p.method },
    {
      key: "status",
      header: "Statut",
      cell: (p) => (
        <div className="flex flex-col items-start gap-1">
          <Badge tone={p.status === "CANCELLED" ? "danger" : "success"}>{PAYMENT_STATUS_LABELS[p.status] ?? p.status}</Badge>
          {p.status === "CANCELLED" && p.cancellation_reason && <span className="text-xs text-slate-600">Motif : {p.cancellation_reason}</span>}
        </div>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      mobile: "full",
      cell: (p) => (
        <div className="flex flex-wrap gap-2 sm:justify-end">
          <Button variant="secondary" size="sm" icon="download" onClick={() => onDownload(p.id)}>
            Reçu
          </Button>
          {canManage && p.status === "COMPLETED" && (
            <Button variant="quietDanger" size="sm" onClick={() => onCancel(p)}>
              Annuler
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-base font-bold text-slate-900">Historique des paiements</h3>
      <DataTable
        caption="Historique des paiements"
        columns={columns}
        rows={items}
        rowKey={(p) => p.id}
        rowTone={(p) => (p.status === "CANCELLED" ? "muted" : undefined)}
        empty={<EmptyState icon="receipt" title="Aucun paiement enregistré." />}
      />
    </div>
  );
}
