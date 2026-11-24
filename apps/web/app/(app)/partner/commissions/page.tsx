"use client";

import { DataTable, TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Badge, EmptyState, PageHeader, StatCard, type Tone } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { COMMISSION_STATUS_LABELS, SETTLEMENT_METHOD_LABELS, partnerCommissions, type CommissionStatus } from "@/lib/commissions/client";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";

const STATUS_TONES: Record<CommissionStatus, Tone> = { DUE: "warning", PAID: "success", CANCELLED: "neutral" };

// Espace partenaire : ses propres commissions (le partenaire est dérivé du compte connecté côté
// API, jamais d'un paramètre). Lecture seule. Phase 4 A (2026-11-24) : cartes d'indicateurs et
// tableau commun (cartes sur téléphone).
export default function PartnerCommissionsPage() {
  const { data, error, isLoading, retry } = useAsyncData(() => partnerCommissions.own(), []);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Mes commissions"
        description="Commission sur le montant HT de chaque abonnement payé par une école que vous avez inscrite."
      />

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <TableSkeleton />}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard icon="percent" label="Votre taux" value={`${Number(data.commission_rate)} %`} />
            <StatCard
              icon="clock"
              tone="warning"
              label={`À recevoir (${data.totals.due_count})`}
              value={formatApiAmount(data.totals.due_amount, "XOF")}
            />
            <StatCard
              icon="checkSquare"
              tone="success"
              label={`Déjà reçues (${data.totals.paid_count})`}
              value={formatApiAmount(data.totals.paid_amount, "XOF")}
            />
          </div>

          <DataTable
            caption="Mes commissions"
            rows={data.items}
            rowKey={(item) => item.id}
            rowTone={(item) => (item.status === "CANCELLED" ? "muted" : undefined)}
            empty={<EmptyState icon="percent" title="Aucune commission pour l'instant." />}
            columns={[
              { key: "school", header: "École", mobile: "title", cell: (item) => item.school_name },
              { key: "date", header: "Date", cell: (item) => formatDateFR(item.created_at) },
              {
                key: "invoice",
                header: "Facture",
                cell: (item) => `${item.invoice_number ?? "—"} (${item.period_months} mois)`,
              },
              { key: "base", header: "Montant HT", align: "right", cell: (item) => formatApiAmount(item.base_amount_excl_vat, item.currency) },
              { key: "rate", header: "Taux", align: "right", cell: (item) => `${Number(item.rate)} %` },
              {
                key: "amount",
                header: "Commission",
                align: "right",
                cell: (item) => <span className="font-semibold text-slate-900">{formatApiAmount(item.amount, item.currency)}</span>,
              },
              {
                key: "status",
                header: "Statut",
                cell: (item) => (
                  <div className="flex flex-col items-start gap-1">
                    <Badge tone={STATUS_TONES[item.status]}>{COMMISSION_STATUS_LABELS[item.status]}</Badge>
                    {item.status === "PAID" && item.settlement_method && (
                      <span className="text-xs text-slate-600">
                        {SETTLEMENT_METHOD_LABELS[item.settlement_method]} — {item.settlement_reference}
                        {item.paid_at && `, le ${formatDateFR(item.paid_at)}`}
                      </span>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
