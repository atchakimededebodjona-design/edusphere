"use client";

import { useEffect, useRef, useState } from "react";
import { openReceipt } from "@/components/cashier/receipt";
import { Button } from "@/components/ui/Button";
import { DataTable, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { Modal } from "@/components/ui/Dialog";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { SelectField, TextField } from "@/components/ui/Field";
import { Badge, EmptyState, PageHeader, StatCard } from "@/components/ui/Surface";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import { cancelPaymentErrorMessage } from "@/lib/fees/cancelErrors";
import { feesSummary, payments as paymentsClient, type FeesSummary, type Payment, type PaymentStatus } from "@/lib/fees/client";
import { PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";

export default function PaymentsPage() {
  const { currentSchoolId, currentSchool, permissions } = useAuth();
  // Même permission que celle exigée par POST /payments/{id}/cancel (lot 1 : `payments.cancel`,
  // distincte de `payments.manage` qui ne couvre que l'enregistrement). Affichage seulement : l'API
  // reste l'autorité.
  const canCancel = permissions.includes("payments.cancel");
  const currency = currentSchool?.currency ?? "";
  const [items, setItems] = useState<Payment[] | null>(null);
  const [summary, setSummary] = useState<FeesSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState<PaymentStatus | "">("");
  const [loadError, setLoadError] = useState<string | null>(null);
  // Annulation : un seul envoi par paiement à la fois (double clic, clics concurrents), bouton
  // désactivé pendant la requête, erreur affichée sans jamais présenter l'annulation comme faite.
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<{ receipt: string; message: string } | null>(null);
  const cancelInFlight = useRef<Set<string>>(new Set());
  // Phase 3 (2026-11-24) — le motif se saisit dans une fenêtre de l'application, plus dans la boîte
  // `window.prompt` du navigateur.
  const [cancelTarget, setCancelTarget] = useState<Payment | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [receiptError, setReceiptError] = useState<string | null>(null);

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
    setReceiptError(null);
    try {
      await openReceipt(paymentId);
    } catch (err) {
      setReceiptError(toErrorMessage(err));
    }
  }

  function askCancel(payment: Payment) {
    if (cancelInFlight.current.has(payment.id)) return;
    setCancelReason("");
    setCancelTarget(payment);
  }

  async function handleCancel(payment: Payment, reason: string) {
    if (!currentSchoolId || !reason || cancelInFlight.current.has(payment.id)) return;
    cancelInFlight.current.add(payment.id);
    setCancelTarget(null);
    try {
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

  const columns: Column<Payment>[] = [
    { key: "receipt", header: "Reçu", mobile: "title", cell: (p) => <span className="font-medium text-slate-900">{p.receipt_number}</span> },
    { key: "date", header: "Date", cell: (p) => formatDateFR(p.paid_at) },
    {
      key: "amount",
      header: "Montant",
      align: "right",
      cell: (p) => (
        <span className={`font-semibold ${p.status === "CANCELLED" ? "text-slate-600 line-through" : "text-slate-900"}`}>
          {formatApiAmount(p.amount, currency)}
        </span>
      ),
    },
    { key: "method", header: "Mode", cell: (p) => PAYMENT_METHOD_LABELS[p.method] ?? p.method },
    {
      key: "status",
      header: "Statut",
      cell: (p) => (
        <div className="flex flex-col items-start gap-1">
          <Badge tone={p.status === "CANCELLED" ? "danger" : "success"}>{PAYMENT_STATUS_LABELS[p.status] ?? p.status}</Badge>
          {p.status === "CANCELLED" && p.cancellation_reason && (
            <span className="text-xs text-slate-600">Motif : {p.cancellation_reason}</span>
          )}
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
          <Button variant="secondary" size="sm" icon="download" onClick={() => void handleDownload(p.id)}>
            Reçu
          </Button>
          {canCancel && p.status === "COMPLETED" && (
            <Button
              variant="quietDanger"
              size="sm"
              onClick={() => askCancel(p)}
              disabled={cancellingId === p.id}
              aria-busy={cancellingId === p.id}
            >
              {cancellingId === p.id ? "Annulation..." : "Annuler"}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Paiements" description="Tous les paiements enregistrés pour l'école, avec leur reçu." />

      {cancelError && (
        <div
          role="alert"
          data-testid="payment-cancel-error"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <span>
            Reçu {cancelError.receipt} — {cancelError.message}
          </span>
          <Button variant="secondary" size="sm" onClick={() => setCancelError(null)}>
            Fermer
          </Button>
        </div>
      )}
      {receiptError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {receiptError}
        </p>
      )}

      {summary === null ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-200 motion-reduce:animate-none" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard icon="wallet" label="Total facturé" value={formatApiAmount(summary.total_due, currency)} />
          <StatCard icon="cash" tone="success" label="Total encaissé" value={formatApiAmount(summary.total_paid, currency)} />
          <StatCard icon="receipt" tone="warning" label="Solde global" value={formatApiAmount(summary.balance, currency)} />
          <StatCard
            icon="clock"
            tone={summary.overdue_count > 0 ? "danger" : "info"}
            label="Échéances dépassées"
            value={summary.overdue_count}
          />
        </div>
      )}

      <div className="w-full sm:max-w-xs">
        <SelectField label="Statut" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as PaymentStatus | "")}>
          <option value="">Tous</option>
          <option value="COMPLETED">Enregistrés</option>
          <option value="CANCELLED">Annulés</option>
        </SelectField>
      </div>

      {!currentSchoolId || items === null ? (
        <TableSkeleton />
      ) : (
        <DataTable
          caption="Paiements"
          columns={columns}
          rows={items}
          rowKey={(p) => p.id}
          rowTone={(p) => (p.status === "CANCELLED" ? "muted" : undefined)}
          empty={<EmptyState icon="receipt" title="Aucun paiement." description="Les encaissements faits à la caisse apparaîtront ici." />}
        />
      )}

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
              Reçu <strong>{cancelTarget.receipt_number}</strong>, {formatApiAmount(cancelTarget.amount, currency)}. Le paiement
              restera dans la liste, marqué « Annulé », et ne comptera plus dans les totaux.
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
              <Button variant="secondary" onClick={() => setCancelTarget(null)}>
                Retour
              </Button>
              <Button type="submit" variant="danger" disabled={cancelReason.trim() === ""}>
                Confirmer l&apos;annulation
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
