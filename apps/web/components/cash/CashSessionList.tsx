import type { CashSessionSummary } from "@/lib/cash/client";
import { CASH_SESSION_STATUS_LABELS, CASH_VARIANCE_REASON_LABELS } from "@/lib/cash/labels";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";

function formatDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—";
}

function amount(value: string | null, currency: string): string {
  return value === null ? "—" : formatApiAmount(value, currency);
}

/** Historique / supervision des sessions : tableau sur grand écran, cartes sur mobile. */
export function CashSessionList({
  sessions,
  currency,
  showCashier,
  onSelect,
  label,
}: {
  sessions: CashSessionSummary[];
  currency: string;
  showCashier: boolean;
  onSelect?: (sessionId: string) => void;
  label: string;
}) {
  if (sessions.length === 0) return <p className="text-sm text-slate-500">Aucune session.</p>;
  const variance = (s: CashSessionSummary) =>
    s.variance_amount === null ? "—" : `${Number(s.variance_amount) > 0 ? "+" : ""}${formatApiAmount(s.variance_amount, currency)}`;

  return (
    <>
      <div className="hidden overflow-x-auto rounded border border-slate-200 bg-white md:block">
        <table aria-label={label} className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-medium text-slate-600">
            <tr>
              <th className="px-3 py-2">Date</th>
              {showCashier && <th className="px-3 py-2">Caissier</th>}
              <th className="px-3 py-2">Statut</th>
              <th className="px-3 py-2 text-right">Fonds initial</th>
              <th className="px-3 py-2 text-right">Encaissements</th>
              <th className="px-3 py-2 text-right">Mouvements (+/−)</th>
              <th className="px-3 py-2 text-right">Théorique</th>
              <th className="px-3 py-2 text-right">Physique</th>
              <th className="px-3 py-2 text-right">Écart</th>
              <th className="px-3 py-2">Clôture</th>
              {onSelect && <th className="px-3 py-2" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sessions.map((s) => (
              <tr key={s.id} data-testid="cash-session-row">
                <td className="px-3 py-2">{formatDateFR(s.business_date)}</td>
                {showCashier && <td className="px-3 py-2">{s.cashier_name ?? "—"}</td>}
                <td className="px-3 py-2">{CASH_SESSION_STATUS_LABELS[s.status]}</td>
                <td className="px-3 py-2 text-right">{amount(s.opening_amount, currency)}</td>
                <td className="px-3 py-2 text-right">
                  {amount(s.cash_payments_total, currency)} <span className="text-xs text-slate-500">({s.cash_payments_count})</span>
                </td>
                <td className="px-3 py-2 text-right">
                  +{amount(s.movements_in_total, currency)} / −{amount(s.movements_out_total, currency)}
                </td>
                <td className="px-3 py-2 text-right">{amount(s.current_expected_amount, currency)}</td>
                <td className="px-3 py-2 text-right">{amount(s.counted_amount, currency)}</td>
                <td className="px-3 py-2 text-right" title={s.variance_note ?? undefined}>
                  {variance(s)}
                  {s.variance_reason && (
                    <span className="block text-xs text-slate-500">{CASH_VARIANCE_REASON_LABELS[s.variance_reason]}</span>
                  )}
                </td>
                <td className="px-3 py-2">{formatDateTime(s.closed_at)}</td>
                {onSelect && (
                  <td className="px-3 py-2 text-right">
                    <button type="button" onClick={() => onSelect(s.id)} className="text-xs text-slate-700 underline">
                      Détail
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul aria-label={label} className="flex flex-col gap-2 md:hidden">
        {sessions.map((s) => (
          <li key={s.id} className="rounded border border-slate-200 bg-white p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold text-slate-900">
                {formatDateFR(s.business_date)}
                {showCashier && s.cashier_name ? ` · ${s.cashier_name}` : ""}
              </p>
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{CASH_SESSION_STATUS_LABELS[s.status]}</span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
              <dt className="text-slate-500">Fonds initial</dt>
              <dd className="text-right">{amount(s.opening_amount, currency)}</dd>
              <dt className="text-slate-500">Encaissements</dt>
              <dd className="text-right">{amount(s.cash_payments_total, currency)}</dd>
              <dt className="text-slate-500">Théorique</dt>
              <dd className="text-right">{amount(s.current_expected_amount, currency)}</dd>
              <dt className="text-slate-500">Physique</dt>
              <dd className="text-right">{amount(s.counted_amount, currency)}</dd>
              <dt className="text-slate-500">Écart</dt>
              <dd className="text-right font-semibold">{variance(s)}</dd>
              <dt className="text-slate-500">Clôture</dt>
              <dd className="text-right">{formatDateTime(s.closed_at)}</dd>
            </dl>
            {onSelect && (
              <button type="button" onClick={() => onSelect(s.id)} className="mt-2 text-xs text-slate-700 underline">
                Détail
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
