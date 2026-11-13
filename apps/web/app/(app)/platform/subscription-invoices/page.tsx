"use client";

import { useState, type ReactNode } from "react";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";
import {
  INVOICE_STATUS_LABELS,
  MANUAL_METHOD_LABELS,
  periodLabel,
  platformSubscriptions,
  type InvoiceStatus,
  type ManualPaymentMethod,
  type PlatformInvoice,
} from "@/lib/subscriptions/client";
import { PlatformListPage } from "../PlatformListPage";

const STATUSES = Object.keys(INVOICE_STATUS_LABELS) as InvoiceStatus[];
const METHODS = Object.keys(MANUAL_METHOD_LABELS) as ManualPaymentMethod[];

type Action =
  | { kind: "quote"; invoice: PlatformInvoice; amount: string }
  | { kind: "pay"; invoice: PlatformInvoice; method: ManualPaymentMethod; reference: string; key: string }
  | { kind: "cancel"; invoice: PlatformInvoice; reason: string };

// Phase 29, lot A — factures d'abonnement (PLATFORM_OWNER) : chiffrage des devis, enregistrement
// d'un paiement reçu hors application (virement, Mobile Money, espèces), annulation d'une facture non
// payée. Le montant d'un paiement est TOUJOURS celui de la facture (refus côté API sinon).
export default function PlatformSubscriptionInvoicesPage() {
  const { permissions } = useAuth();
  const canManage = permissions.includes("platform.subscriptions.manage");
  const [status, setStatus] = useState<InvoiceStatus | "">("");
  const [reloadKey, setReloadKey] = useState(0);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function submit() {
    if (!action) return;
    setBusy(true);
    setActionError(null);
    try {
      if (action.kind === "quote") {
        await platformSubscriptions.setQuote(action.invoice.id, action.amount);
      } else if (action.kind === "pay") {
        await platformSubscriptions.recordManualPayment(action.invoice.id, {
          method: action.method,
          amount: action.invoice.total_amount ?? "0",
          reference: action.reference,
          idempotency_key: action.key,
        });
      } else {
        await platformSubscriptions.cancel(action.invoice.id, action.reason);
      }
      setAction(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function actionsFor(invoice: PlatformInvoice) {
    if (!canManage) return "—";
    const open = (next: Action) => {
      setActionError(null);
      setAction(next);
    };
    const buttons: ReactNode[] = [];
    if (invoice.status === "QUOTE_REQUIRED") {
      buttons.push(
        <button key="quote" type="button" onClick={() => open({ kind: "quote", invoice, amount: "" })} className="text-sky-700 underline">
          Chiffrer le devis
        </button>,
      );
    }
    if (invoice.status === "ISSUED") {
      buttons.push(
        <button
          key="pay"
          type="button"
          onClick={() =>
            open({ kind: "pay", invoice, method: "BANK_TRANSFER", reference: "", key: platformSubscriptions.newIdempotencyKey() })
          }
          className="text-emerald-700 underline"
        >
          Enregistrer le paiement
        </button>,
      );
    }
    if (invoice.status === "ISSUED" || invoice.status === "QUOTE_REQUIRED") {
      buttons.push(
        <button key="cancel" type="button" onClick={() => open({ kind: "cancel", invoice, reason: "" })} className="text-red-700 underline">
          Annuler
        </button>,
      );
    }
    return buttons.length ? <div className="flex flex-wrap gap-2">{buttons}</div> : "—";
  }

  return (
    <PlatformListPage<PlatformInvoice>
      title="Factures d'abonnement"
      description="Factures émises par les écoles : devis à chiffrer, paiements à enregistrer, annulations."
      fetchPage={(page, pageSize) => platformSubscriptions.invoices(page, pageSize, status)}
      rowKey={(invoice) => invoice.id}
      reloadKey={reloadKey}
      columns={[
        { header: "Numéro", render: (invoice) => invoice.number ?? "Devis" },
        { header: "École", render: (invoice) => invoice.school_name },
        { header: "Durée", render: (invoice) => periodLabel(invoice.period_months) },
        { header: "Effectif", render: (invoice) => String(invoice.student_count) },
        {
          header: "Montant",
          render: (invoice) => (invoice.total_amount ? formatApiAmount(invoice.total_amount, invoice.currency) : "—"),
        },
        { header: "Statut", render: (invoice) => INVOICE_STATUS_LABELS[invoice.status] },
        {
          header: "Période",
          render: (invoice) =>
            invoice.period ? `${formatDateFR(invoice.period.starts_on)} → ${formatDateFR(invoice.period.ends_on)}` : "—",
        },
        { header: "Actions", render: actionsFor },
      ]}
    >
      <label className="flex items-center gap-2 text-sm text-slate-700">
        Statut
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as InvoiceStatus | "");
            setReloadKey((k) => k + 1);
          }}
          className="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">Tous</option>
          {STATUSES.map((code) => (
            <option key={code} value={code}>
              {INVOICE_STATUS_LABELS[code]}
            </option>
          ))}
        </select>
      </label>

      {action && (
        <section className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4 text-sm">
          <p className="font-medium text-slate-900">
            {action.invoice.school_name} — {action.invoice.number ?? "devis"} ({periodLabel(action.invoice.period_months)},{" "}
            {action.invoice.student_count} élèves)
          </p>
          {action.kind === "quote" && (
            <label className="flex flex-col gap-1">
              Montant du devis (FCFA entiers)
              <input
                inputMode="numeric"
                value={action.amount}
                onChange={(e) => setAction({ ...action, amount: e.target.value.replace(/[^\d]/g, "") })}
                className="w-48 rounded border border-slate-300 px-2 py-1"
              />
            </label>
          )}
          {action.kind === "pay" && (
            <>
              <p>
                Montant reçu : <strong>{formatApiAmount(action.invoice.total_amount ?? "0", action.invoice.currency)}</strong>{" "}
                (montant exact de la facture).
              </p>
              <label className="flex flex-col gap-1">
                Moyen de paiement
                <select
                  value={action.method}
                  onChange={(e) => setAction({ ...action, method: e.target.value as ManualPaymentMethod })}
                  className="w-56 rounded border border-slate-300 px-2 py-1"
                >
                  {METHODS.map((method) => (
                    <option key={method} value={method}>
                      {MANUAL_METHOD_LABELS[method]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                Référence (n° de virement, de transaction…)
                <input
                  value={action.reference}
                  maxLength={255}
                  onChange={(e) => setAction({ ...action, reference: e.target.value })}
                  className="w-72 rounded border border-slate-300 px-2 py-1"
                />
              </label>
            </>
          )}
          {action.kind === "cancel" && (
            <label className="flex flex-col gap-1">
              Motif de l&apos;annulation
              <input
                value={action.reason}
                maxLength={500}
                onChange={(e) => setAction({ ...action, reason: e.target.value })}
                className="w-96 max-w-full rounded border border-slate-300 px-2 py-1"
              />
            </label>
          )}
          {actionError && <p className="text-red-700">{actionError}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="rounded bg-slate-900 px-3 py-2 font-medium text-white disabled:opacity-50"
            >
              Confirmer
            </button>
            <button type="button" disabled={busy} onClick={() => setAction(null)} className="rounded border border-slate-300 px-3 py-2">
              Fermer
            </button>
          </div>
        </section>
      )}
    </PlatformListPage>
  );
}
