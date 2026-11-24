"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage, useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import {
  COMMISSION_STATUS_LABELS,
  SETTLEMENT_METHOD_LABELS,
  platformCommissions,
  type Commission,
  type CommissionStatus,
  type SettlementMethod,
} from "@/lib/commissions/client";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";
import { listPlatformPartners } from "@/lib/platform/client";

const PAGE_SIZE = 50;
const STATUSES = Object.keys(COMMISSION_STATUS_LABELS) as CommissionStatus[];
const METHODS = Object.keys(SETTLEMENT_METHOD_LABELS) as SettlementMethod[];

// Commissions des partenaires (migration 0031) : taux du partenaire × HT de chaque facture
// d'abonnement payée d'une école qu'il a inscrite. Versement MANUEL : vous payez le partenaire hors
// application, puis vous marquez ici les commissions versées avec la référence. Contrôles réels
// côté API (`platform.commissions.read|manage`).
export default function PlatformCommissionsPage() {
  const { permissions } = useAuth();
  const canManage = permissions.includes("platform.commissions.manage");
  const [status, setStatus] = useState<CommissionStatus | "">("DUE");
  const [partnerId, setPartnerId] = useState("");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [method, setMethod] = useState<SettlementMethod>("MOBILE_MONEY");
  const [reference, setReference] = useState("");
  const [cancelling, setCancelling] = useState<{ id: string; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const partners = useAsyncData(() => listPlatformPartners(1, 100), []);
  const { data, error, isLoading, retry } = useAsyncData(
    () => platformCommissions.list(page, PAGE_SIZE, status, partnerId),
    [page, status, partnerId, reloadKey],
  );

  const selectedRows = (data?.items ?? []).filter((item) => selected.has(item.id));
  const selectedPartners = new Set(selectedRows.map((item) => item.partner_id));
  const selectedTotal = selectedRows.reduce((sum, item) => sum + Number(item.amount), 0);

  function refresh() {
    setSelected(new Set());
    setReloadKey((k) => k + 1);
  }

  function toggle(item: Commission) {
    const next = new Set(selected);
    if (next.has(item.id)) next.delete(item.id);
    else next.add(item.id);
    setSelected(next);
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      refresh();
    } catch (err) {
      setActionError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function settle() {
    if (selectedPartners.size !== 1) {
      setActionError("Un versement concerne les commissions d'un seul partenaire : filtrez par partenaire.");
      return;
    }
    if (!reference.trim()) {
      setActionError("Indiquez la référence du versement (numéro de transaction, de virement…).");
      return;
    }
    return run(async () => {
      await platformCommissions.markPaid([...selected], method, reference.trim());
      setReference("");
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Commissions des partenaires</h1>
        <p className="text-sm text-slate-600">
          Taux du partenaire appliqué au montant HT de chaque abonnement payé par une école qu&apos;il a inscrite. Versez la
          commission hors application, puis marquez-la ici comme versée avec sa référence.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700">
        <label className="flex items-center gap-2">
          Statut
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as CommissionStatus | "");
              setPage(1);
              setSelected(new Set());
            }}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">Tous</option>
            {STATUSES.map((code) => (
              <option key={code} value={code}>
                {COMMISSION_STATUS_LABELS[code]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Partenaire
          <select
            value={partnerId}
            onChange={(e) => {
              setPartnerId(e.target.value);
              setPage(1);
              setSelected(new Set());
            }}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">Tous</option>
            {partners.data?.items.map((partner) => (
              <option key={partner.id} value={partner.id}>
                {partner.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {data && (
        <p className="text-sm text-slate-700">
          {partnerId ? "Pour ce partenaire" : "Tous partenaires"} — à verser :{" "}
          <strong>{formatApiAmount(data.totals.due_amount, "XOF")}</strong> ({data.totals.due_count}) · déjà versées :{" "}
          {formatApiAmount(data.totals.paid_amount, "XOF")} ({data.totals.paid_count})
        </p>
      )}

      {actionError && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{actionError}</p>}

      {canManage && selected.size > 0 && (
        <section className="flex flex-wrap items-end gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
          <p className="w-full text-emerald-900">
            {selected.size} commission{selected.size > 1 ? "s" : ""} sélectionnée{selected.size > 1 ? "s" : ""} :{" "}
            <strong>{formatApiAmount(String(selectedTotal), "XOF")}</strong>
            {selectedPartners.size > 1 && " — attention : plusieurs partenaires, un versement n'en concerne qu'un."}
          </p>
          <label className="flex flex-col gap-1">
            Moyen
            <select value={method} onChange={(e) => setMethod(e.target.value as SettlementMethod)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500">
              {METHODS.map((code) => (
                <option key={code} value={code}>
                  {SETTLEMENT_METHOD_LABELS[code]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Référence du versement
            <input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={255} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 sm:!w-64" />
          </label>
          <button type="button" disabled={busy} onClick={settle} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
            Marquer comme versées
          </button>
        </section>
      )}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-600">Chargement...</p>}
      {data && data.items.length === 0 && <p className="text-sm text-slate-600">Aucune commission.</p>}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["", "Date", "Partenaire", "École", "Facture", "HT", "Taux", "Commission", "Statut", ""].map((h, i) => (
                  <th key={i} className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-2">
                    {canManage && item.status === "DUE" && (
                      <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item)} aria-label="Sélectionner" />
                    )}
                  </td>
                  <td className="px-3 py-2">{formatDateFR(item.created_at)}</td>
                  <td className="px-3 py-2">{item.partner_name}</td>
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
                      <span className="block text-xs text-slate-600">
                        {SETTLEMENT_METHOD_LABELS[item.settlement_method]} — {item.settlement_reference}
                        {item.paid_at && `, le ${formatDateFR(item.paid_at)}`}
                      </span>
                    )}
                    {item.status === "CANCELLED" && <span className="block text-xs text-slate-600">{item.cancel_reason}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {canManage && item.status === "DUE" &&
                      (cancelling?.id === item.id ? (
                        <span className="flex items-center gap-2">
                          <input
                            value={cancelling.reason}
                            onChange={(e) => setCancelling({ id: item.id, reason: e.target.value })}
                            placeholder="Motif"
                            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 !w-40"
                          />
                          <button
                            type="button"
                            disabled={busy || cancelling.reason.trim().length < 3}
                            onClick={() =>
                              run(async () => {
                                const response = await platformCommissions.cancel(item.id, cancelling.reason.trim());
                                if (!response.ok) throw new Error("Annulation refusée");
                                setCancelling(null);
                              })
                            }
                            className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Confirmer
                          </button>
                        </span>
                      ) : (
                        <button type="button" onClick={() => setCancelling({ id: item.id, reason: "" })} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                          Annuler
                        </button>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
            Précédente
          </button>
          <span>
            Page {data.page} / {data.total_pages}
          </span>
          <button
            type="button"
            disabled={page >= data.total_pages}
            onClick={() => setPage(page + 1)}
            className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Suivante
          </button>
        </div>
      )}
    </div>
  );
}
