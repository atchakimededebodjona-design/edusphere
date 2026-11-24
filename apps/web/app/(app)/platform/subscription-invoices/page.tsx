"use client";

import { useState, type ReactNode } from "react";
import { INVOICE_STATUS_TONES } from "@/components/subscriptions/tones";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Dialog";
import { SelectField, TextField } from "@/components/ui/Field";
import { Alert, Badge } from "@/components/ui/Surface";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";
import {
  INVOICE_STATUS_LABELS,
  MANUAL_METHOD_LABELS,
  PAYMENT_STATUS_LABELS,
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
// Lot B — colonne « Mobile Money » : dernière tentative PayGate. Une ANOMALIE (paiement réussi chez
// PayGate mais non appliqué : montant différent ou facture déjà payée) se régularise depuis le tableau
// de bord PayGate ; le détail figure dans le journal d'audit de l'école.
function onlinePaymentCell(invoice: PlatformInvoice): ReactNode {
  const online = invoice.payments.filter((payment) => payment.provider === "PAYGATE");
  if (online.length === 0) return "—";
  const anomalies = online.filter((payment) => payment.status === "ANOMALY").length;
  const last = online[online.length - 1];
  return (
    <span className={anomalies ? "font-semibold text-red-700" : "text-slate-800"}>
      {anomalies ? `${anomalies} anomalie${anomalies > 1 ? "s" : ""} à traiter` : PAYMENT_STATUS_LABELS[last.status]}
      {last.payer_phone_last4 ? ` (•• ${last.payer_phone_last4})` : ""}
    </span>
  );
}

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
        <Button key="quote" variant="quiet" size="sm" onClick={() => open({ kind: "quote", invoice, amount: "" })}>
          Chiffrer le devis
        </Button>,
      );
    }
    if (invoice.status === "ISSUED") {
      buttons.push(
        <Button
          key="pay"
          variant="quiet"
          size="sm"
          onClick={() =>
            open({ kind: "pay", invoice, method: "BANK_TRANSFER", reference: "", key: platformSubscriptions.newIdempotencyKey() })
          }
        >
          Enregistrer le paiement
        </Button>,
      );
    }
    if (invoice.status === "PAID") {
      buttons.push(
        <Button
          key="receipt"
          variant="secondary"
          size="sm"
          icon="download"
          onClick={async () => {
            setActionError(null);
            // Onglet ouvert AVANT l'appel réseau (geste encore actif : pas de blocage des fenêtres
            // surgissantes sur téléphone), puis dirigé vers le reçu — comme à la caisse.
            const tab = window.open("", "_blank");
            try {
              const url = await platformSubscriptions.receiptBlobUrl(invoice.id);
              if (tab) tab.location.href = url;
              else window.open(url, "_blank", "noopener");
            } catch (err) {
              tab?.close();
              setActionError(toErrorMessage(err));
            }
          }}
        >
          Reçu
        </Button>,
      );
    }
    if (invoice.status === "ISSUED" || invoice.status === "QUOTE_REQUIRED") {
      buttons.push(
        <Button key="cancel" variant="quietDanger" size="sm" onClick={() => open({ kind: "cancel", invoice, reason: "" })}>
          Annuler
        </Button>,
      );
    }
    return buttons.length ? <div className="flex flex-wrap gap-2 max-sm:-ml-2">{buttons}</div> : "—";
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
        { header: "Effectif", align: "right", render: (invoice) => String(invoice.student_count) },
        {
          header: "Montant",
          align: "right",
          render: (invoice) => (invoice.total_amount ? formatApiAmount(invoice.total_amount, invoice.currency) : "—"),
        },
        {
          header: "Statut",
          render: (invoice) => <Badge tone={INVOICE_STATUS_TONES[invoice.status]}>{INVOICE_STATUS_LABELS[invoice.status]}</Badge>,
        },
        { header: "Mobile Money", render: onlinePaymentCell },
        {
          header: "Période",
          render: (invoice) =>
            invoice.period ? `${formatDateFR(invoice.period.starts_on)} → ${formatDateFR(invoice.period.ends_on)}` : "—",
        },
        { header: "Actions", mobile: "full", render: actionsFor },
      ]}
    >
      <div className="w-full sm:max-w-xs">
        <SelectField
          label="Statut"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as InvoiceStatus | "");
            setReloadKey((k) => k + 1);
          }}
        >
          <option value="">Tous</option>
          {STATUSES.map((code) => (
            <option key={code} value={code}>
              {INVOICE_STATUS_LABELS[code]}
            </option>
          ))}
        </SelectField>
      </div>

      {actionError && !action && <Alert tone="danger">{actionError}</Alert>}

      {/* Phase 4 A (2026-11-24) — l'action se fait dans la fenêtre commune, à côté de la facture choisie,
          au lieu d'un panneau ouvert au-dessus du tableau. Même logique et mêmes contrôles qu'avant. */}
      <Modal
        open={action !== null}
        onClose={() => {
          if (!busy) setAction(null);
        }}
        title={action?.kind === "quote" ? "Chiffrer le devis" : action?.kind === "pay" ? "Enregistrer le paiement" : "Annuler la facture"}
      >
        {action && (
          <form
            className="flex flex-col gap-4 text-sm"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <p className="font-medium text-slate-900">
              {action.invoice.school_name} — {action.invoice.number ?? "devis"} ({periodLabel(action.invoice.period_months)},{" "}
              {action.invoice.student_count} élèves)
            </p>
            {action.kind === "quote" && (
              <TextField
                label="Montant du devis (FCFA entiers)"
                inputMode="numeric"
                value={action.amount}
                data-autofocus
                onChange={(e) => setAction({ ...action, amount: e.target.value.replace(/[^\d]/g, "") })}
              />
            )}
            {action.kind === "pay" && (
              <>
                <p className="text-slate-700">
                  Montant reçu : <strong>{formatApiAmount(action.invoice.total_amount ?? "0", action.invoice.currency)}</strong>{" "}
                  (montant exact de la facture).
                </p>
                <SelectField
                  label="Moyen de paiement"
                  value={action.method}
                  onChange={(e) => setAction({ ...action, method: e.target.value as ManualPaymentMethod })}
                >
                  {METHODS.map((method) => (
                    <option key={method} value={method}>
                      {MANUAL_METHOD_LABELS[method]}
                    </option>
                  ))}
                </SelectField>
                <TextField
                  label="Référence (n° de virement, de transaction…)"
                  value={action.reference}
                  maxLength={255}
                  data-autofocus
                  onChange={(e) => setAction({ ...action, reference: e.target.value })}
                />
              </>
            )}
            {action.kind === "cancel" && (
              <TextField
                label="Motif de l'annulation"
                value={action.reason}
                maxLength={500}
                data-autofocus
                onChange={(e) => setAction({ ...action, reason: e.target.value })}
              />
            )}
            {actionError && <Alert tone="danger">{actionError}</Alert>}
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="secondary" disabled={busy} onClick={() => setAction(null)}>
                Fermer
              </Button>
              <Button type="submit" variant={action.kind === "cancel" ? "danger" : "primary"} disabled={busy}>
                {busy ? "Un instant..." : "Confirmer"}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </PlatformListPage>
  );
}
