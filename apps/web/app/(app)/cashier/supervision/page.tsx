"use client";

import { useCallback, useEffect, useState } from "react";
import { CashSessionList } from "@/components/cash/CashSessionList";
import { CashTotalsCard } from "@/components/cash/CashTotalsCard";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import {
  cashRegister,
  cashReports,
  type CashDailyReport,
  type CashierReport,
  type CashSessionDetail,
  type CashSessionStatus,
  type CashSessionSummary,
  type PaymentMethodReport,
} from "@/lib/cash/client";
import { CASH_MOVEMENT_TYPE_LABELS } from "@/lib/cash/labels";
import { formatApiAmount } from "@/lib/fees/allocation";
import { PAYMENT_METHOD_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";

type Data = {
  sessions: CashSessionSummary[];
  daily: CashDailyReport;
  cashiers: CashierReport;
  methods: PaymentMethodReport;
};

// Caisse scolaire, lot 3 — supervision (`cash.register.review`) : toutes les caisses de l'école,
// rapport du jour, par caissier, par méthode, export CSV. Tous les totaux viennent d'agrégations
// SQL côté API (jamais d'une somme faite ici sur une liste tronquée).
export default function CashSupervisionPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canReview = permissions.includes("cash.register.review");

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState<CashSessionStatus | "">("");
  const [currency, setCurrency] = useState("");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<CashSessionDetail | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!currentSchoolId) return;
    setError(null);
    try {
      let from = dateFrom;
      let to = dateTo;
      if (!from || !to) {
        // Journée métier de l'école (fuseau School.timezone), fournie par l'API.
        const ctx = await cashRegister.current(currentSchoolId);
        setCurrency(ctx.currency);
        from ||= ctx.business_date;
        to ||= ctx.business_date;
        setDateFrom(from);
        setDateTo(to);
      }
      const [sessions, daily, cashiers, methods] = await Promise.all([
        cashRegister.list(currentSchoolId, { dateFrom: from, dateTo: to, status: status || undefined }),
        cashReports.daily(currentSchoolId, to),
        cashReports.cashiers(currentSchoolId, from, to),
        cashReports.methods(currentSchoolId, from, to),
      ]);
      setCurrency(daily.currency);
      setData({ sessions, daily, cashiers, methods });
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }, [currentSchoolId, dateFrom, dateTo, status]);

  useEffect(() => {
    if (canReview) void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReview, currentSchoolId, status]);

  async function showDetail(sessionId: string) {
    try {
      setDetail(await cashRegister.get(sessionId));
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function exportCsv() {
    if (!currentSchoolId) return;
    setExportError(null);
    try {
      const { url, filename } = await cashReports.downloadCsv(currentSchoolId, dateFrom, dateTo);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(toErrorMessage(err));
    }
  }

  if (!canReview) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Supervision des caisses</h1>
        <p role="alert" className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          Cet espace est réservé aux superviseurs de caisse.
        </p>
      </div>
    );
  }
  if (error) return <ErrorRetry message={error} onRetry={() => void reload()} />;
  if (!data) return <p className="text-sm text-slate-500">Chargement...</p>;

  const s = data.daily.sessions;
  const cards: [string, string][] = [
    ["Sessions (ouvertes / clôturées)", `${s.sessions_count} (${s.open_count} / ${s.closed_count})`],
    ["Fonds initiaux", formatApiAmount(s.opening_total, currency)],
    ["Encaissements espèces", formatApiAmount(s.cash_payments_total, currency)],
    ["Entrées / sorties", `${formatApiAmount(s.movements_in_total, currency)} / ${formatApiAmount(s.movements_out_total, currency)}`],
    ["Théorique", formatApiAmount(s.expected_total, currency)],
    ["Physique (clôturées)", formatApiAmount(s.counted_total, currency)],
    ["Écart (clôturées)", formatApiAmount(s.variance_total, currency)],
  ];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Supervision des caisses</h1>

      <form
        aria-label="Filtres"
        onSubmit={(e) => {
          e.preventDefault();
          void reload();
        }}
        className="flex flex-wrap items-end gap-3 text-xs text-slate-600"
      >
        <label className="flex flex-col gap-1">
          Du
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <label className="flex flex-col gap-1">
          Au
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <label className="flex flex-col gap-1">
          Statut
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as CashSessionStatus | "")}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="">Toutes</option>
            <option value="OPEN">Ouvertes</option>
            <option value="CLOSED">Clôturées</option>
          </select>
        </label>
        <button type="submit" className="rounded bg-slate-900 px-3 py-2 text-sm text-white">
          Afficher
        </button>
        <button type="button" onClick={() => void exportCsv()} className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800">
          Exporter CSV
        </button>
        {exportError && <span className="text-sm text-red-700">{exportError}</span>}
      </form>

      <section aria-labelledby="daily-title" className="flex flex-col gap-2">
        <h2 id="daily-title" className="text-lg font-semibold text-slate-900">
          Journée du {formatDateFR(data.daily.day)}
        </h2>
        <dl data-testid="cash-daily-report" className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-4">
          {cards.map(([label, value]) => (
            <div key={label} className="rounded border border-slate-200 bg-white p-3">
              <dt className="text-xs text-slate-500">{label}</dt>
              <dd className="font-semibold text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="sessions-title" className="flex flex-col gap-2">
        <h2 id="sessions-title" className="text-lg font-semibold text-slate-900">
          Sessions de caisse
        </h2>
        <CashSessionList
          sessions={data.sessions}
          currency={currency}
          showCashier
          onSelect={(id) => void showDetail(id)}
          label="Sessions de caisse"
        />
      </section>

      {detail && (
        <section aria-label="Détail de la session" className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-lg font-semibold text-slate-900">
              Session de {detail.session.cashier_name ?? "—"} du {formatDateFR(detail.session.business_date)}
            </h2>
            <button type="button" onClick={() => setDetail(null)} className="text-xs text-slate-700 underline">
              Fermer
            </button>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <CashTotalsCard totals={detail.totals} currency={currency} />
            <div className="flex flex-col gap-2 text-sm">
              <h3 className="font-semibold text-slate-700">Mouvements</h3>
              {detail.movements.length === 0 && <p className="text-slate-500">Aucun mouvement.</p>}
              <ul className="divide-y divide-slate-100">
                {detail.movements.map((m) => (
                  <li key={m.id} className="flex justify-between gap-2 py-1">
                    <span>
                      {CASH_MOVEMENT_TYPE_LABELS[m.type]} — {m.reason}
                    </span>
                    <span>
                      {m.direction === "IN" ? "+" : "−"}
                      {formatApiAmount(m.amount, currency)}
                    </span>
                  </li>
                ))}
              </ul>
              {detail.latest_count && (
                <>
                  <h3 className="font-semibold text-slate-700">Dernier comptage</h3>
                  <ul className="grid grid-cols-2 gap-1 text-xs">
                    {detail.latest_count.lines.map((line) => (
                      <li key={line.denomination}>
                        {line.quantity} × {formatApiAmount(line.denomination, currency)} = {formatApiAmount(line.line_total, currency)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {detail.session.variance_note && (
                <p className="text-xs text-slate-600">Justification : {detail.session.variance_note}</p>
              )}
            </div>
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="cashiers-title" className="flex flex-col gap-2">
          <h2 id="cashiers-title" className="text-lg font-semibold text-slate-900">
            Par caissier
          </h2>
          {data.cashiers.rows.length === 0 ? (
            <p className="text-sm text-slate-500">Aucune session sur la période.</p>
          ) : (
            <ul aria-label="Rapport par caissier" className="divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
              {data.cashiers.rows.map((row) => (
                <li key={row.cashier_user_id} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                  <span className="font-medium">
                    {row.cashier_name ?? "—"} <span className="text-xs text-slate-500">({row.sessions_count} session(s))</span>
                  </span>
                  <span>
                    {formatApiAmount(row.cash_payments_total, currency)} · écart {formatApiAmount(row.variance_total, currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="methods-title" className="flex flex-col gap-2">
          <h2 id="methods-title" className="text-lg font-semibold text-slate-900">
            Par méthode de paiement
          </h2>
          {data.methods.rows.length === 0 ? (
            <p className="text-sm text-slate-500">Aucun paiement sur la période.</p>
          ) : (
            <ul aria-label="Rapport par méthode" className="divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
              {data.methods.rows.map((row) => (
                <li key={row.method} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                  <span className="font-medium">{PAYMENT_METHOD_LABELS[row.method]}</span>
                  <span>
                    {formatApiAmount(row.completed_total, currency)} ({row.completed_count})
                    {row.cancelled_count > 0 && (
                      <span className="ml-1 text-xs text-slate-500">
                        · annulés {formatApiAmount(row.cancelled_total, currency)} ({row.cancelled_count})
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
