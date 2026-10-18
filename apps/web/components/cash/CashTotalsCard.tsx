import type { CashTotals } from "@/lib/cash/client";
import { formatApiAmount } from "@/lib/fees/allocation";

/** Solde théorique détaillé — la valeur affichée est celle calculée par l'API (règle unique,
 * apps/api/app/modules/cash/service.py::expected_amount_sql), jamais recalculée ici. */
export function CashTotalsCard({ totals, currency }: { totals: CashTotals; currency: string }) {
  const rows: [string, string, string][] = [
    ["Fonds initial", "", totals.opening_amount],
    [`Encaissements espèces (${totals.cash_payments_count})`, "+", totals.cash_payments_total],
    ["Entrées d'espèces", "+", totals.movements_in_total],
    ["Sorties (dépenses, versements banque…)", "−", totals.movements_out_total],
  ];
  return (
    <section aria-labelledby="cash-totals-title" className="rounded border border-slate-200 bg-white p-4">
      <h2 id="cash-totals-title" className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600">
        Solde théorique
      </h2>
      <dl className="flex flex-col gap-1 text-sm">
        {rows.map(([label, sign, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600">
              {sign && <span className="mr-1 font-mono text-slate-400">{sign}</span>}
              {label}
            </dt>
            <dd className="font-medium text-slate-900">{formatApiAmount(value, currency)}</dd>
          </div>
        ))}
        <div className="mt-1 flex justify-between gap-3 border-t border-slate-200 pt-2">
          <dt className="font-semibold text-slate-900">= Solde théorique</dt>
          <dd data-testid="cash-expected-amount" className="text-lg font-bold text-slate-900">
            {formatApiAmount(totals.expected_amount, currency)}
          </dd>
        </div>
      </dl>
    </section>
  );
}
