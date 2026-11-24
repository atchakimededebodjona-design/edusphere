"use client";

import { useCallback, useEffect, useState } from "react";
import { TabSkeleton } from "@/app/parent/children/[id]/ChildAttendance";
import { Button } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Alert, Badge, Card, SectionTitle, StatCard, type Tone } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { formatApiAmount } from "@/lib/fees/allocation";
import type { FinancialSummary, Payment, PaymentStatus, StudentFeeStatus } from "@/lib/fees/client";
import { PAYMENT_STATUS_LABELS, STUDENT_FEE_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";
import { parentChildren } from "@/lib/parent/client";

const FEE_TONES: Record<StudentFeeStatus, Tone> = {
  PAID: "success",
  PARTIALLY_PAID: "warning",
  PENDING: "info",
  CANCELLED: "neutral",
};

const PAYMENT_TONES: Record<PaymentStatus, Tone> = { COMPLETED: "success", CANCELLED: "neutral" };

// L'espace parent ne connaît pas la devise de l'école (pas de lecture de l'école, voir
// parent/children/page.tsx) : les montants sont affichés avec séparateur de milliers, sans unité.
function amount(value: string): string {
  return formatApiAmount(value, "");
}

// Lecture seule uniquement (consigne Phase 28A) : aucun formulaire d'enregistrement de paiement
// ici, contrairement à app/(app)/students/[id]/StudentFinancialSummary.tsx côté admin — le
// backend `/parent/*` n'expose d'ailleurs aucun endpoint d'écriture pour ce module (voir
// parent/router.py, "le parent ne peut jamais créer, modifier, annuler un paiement").
//
// Refonte, phase 2 (2026-11-23) : reste à payer en tête, frais et paiements en lignes lisibles sur
// téléphone (au lieu de tableaux à faire défiler), statuts et dates en français.
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
  if (summary === null || payments === null) return <TabSkeleton />;

  const hasBalance = !/^0+(\.0+)?$/.test(summary.balance.trim());

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard icon="wallet" label="Total dû" value={amount(summary.total_due)} />
        <StatCard icon="checkSquare" tone="success" label="Total payé" value={amount(summary.total_paid)} />
        <StatCard
          icon="chart"
          tone={hasBalance ? "warning" : "success"}
          label="Reste à payer"
          value={amount(summary.balance)}
          hint={hasBalance ? undefined : "Tout est réglé"}
        />
      </div>

      <section aria-labelledby="child-fees-title" className="flex flex-col gap-3">
        <SectionTitle id="child-fees-title" title="Frais" />
        {summary.fees.length === 0 ? (
          <p className="text-sm text-slate-600">Aucun frais affecté à cet élève.</p>
        ) : (
          <Card padded={false}>
            <ul className="divide-y divide-slate-100">
              {summary.fees.map((fee) => (
                <li key={fee.id} className="flex flex-col gap-2 px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-900">{fee.fee_schedule_name}</p>
                      <p className="text-xs text-slate-600">
                        Échéance : {fee.due_date ? formatDateFR(fee.due_date) : "non définie"}
                      </p>
                    </div>
                    <Badge tone={FEE_TONES[fee.status]}>{STUDENT_FEE_STATUS_LABELS[fee.status]}</Badge>
                  </div>
                  <dl className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <dt className="text-slate-600">Dû</dt>
                      <dd className="font-medium tabular-nums text-slate-900">{amount(fee.amount_due)}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-600">Payé</dt>
                      <dd className="font-medium tabular-nums text-slate-900">{amount(fee.amount_paid)}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-600">Reste</dt>
                      <dd className="font-semibold tabular-nums text-slate-900">{amount(fee.balance)}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>

      <section aria-labelledby="child-payments-title" className="flex flex-col gap-3">
        <SectionTitle id="child-payments-title" title="Historique des paiements" />
        {downloadError && <Alert tone="danger">{downloadError}</Alert>}
        {payments.length === 0 ? (
          <p className="text-sm text-slate-600">Aucun paiement enregistré.</p>
        ) : (
          <Card padded={false}>
            <ul className="divide-y divide-slate-100">
              {payments.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-semibold tabular-nums text-slate-900">{amount(p.amount)}</p>
                    <p className="text-xs text-slate-600">
                      {p.receipt_number} · {formatDateFR(p.paid_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={PAYMENT_TONES[p.status]}>{PAYMENT_STATUS_LABELS[p.status]}</Badge>
                    <Button variant="secondary" size="sm" icon="receipt" onClick={() => void handleDownloadReceipt(p.id)}>
                      Reçu
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>
    </div>
  );
}
