"use client";

import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { COMMISSION_STATUS_LABELS, SETTLEMENT_METHOD_LABELS, partnerCommissions } from "@/lib/commissions/client";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";

// Espace partenaire : ses propres commissions (le partenaire est dérivé du compte connecté côté
// API, jamais d'un paramètre). Lecture seule.
export default function PartnerCommissionsPage() {
  const { data, error, isLoading, retry } = useAsyncData(() => partnerCommissions.own(), []);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Mes commissions</h1>
        <p className="text-sm text-slate-600">
          Commission sur le montant HT de chaque abonnement payé par une école que vous avez inscrite.
        </p>
      </div>

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded border border-slate-200 bg-white p-4">
              <p className="text-sm text-slate-600">Votre taux</p>
              <p className="text-xl font-semibold text-slate-900">{Number(data.commission_rate)} %</p>
            </div>
            <div className="rounded border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm text-amber-800">À recevoir ({data.totals.due_count})</p>
              <p className="text-xl font-semibold text-amber-900">{formatApiAmount(data.totals.due_amount, "XOF")}</p>
            </div>
            <div className="rounded border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-sm text-emerald-800">Déjà reçues ({data.totals.paid_count})</p>
              <p className="text-xl font-semibold text-emerald-900">{formatApiAmount(data.totals.paid_amount, "XOF")}</p>
            </div>
          </div>

          {data.items.length === 0 ? (
            <p className="text-sm text-slate-500">Aucune commission pour l&apos;instant.</p>
          ) : (
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    {["Date", "École", "Facture", "Montant HT", "Taux", "Commission", "Statut"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-slate-600">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((item) => (
                    <tr key={item.id}>
                      <td className="px-3 py-2">{formatDateFR(item.created_at)}</td>
                      <td className="px-3 py-2">{item.school_name}</td>
                      <td className="px-3 py-2">
                        {item.invoice_number ?? "—"} ({item.period_months} mois)
                      </td>
                      <td className="px-3 py-2">{formatApiAmount(item.base_amount_excl_vat, item.currency)}</td>
                      <td className="px-3 py-2">{Number(item.rate)} %</td>
                      <td className="px-3 py-2 font-medium">{formatApiAmount(item.amount, item.currency)}</td>
                      <td className="px-3 py-2">
                        {COMMISSION_STATUS_LABELS[item.status]}
                        {item.status === "PAID" && item.settlement_method && (
                          <span className="block text-xs text-slate-500">
                            {SETTLEMENT_METHOD_LABELS[item.settlement_method]} — {item.settlement_reference}
                            {item.paid_at && `, le ${formatDateFR(item.paid_at)}`}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
