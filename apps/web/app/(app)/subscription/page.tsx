"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage, useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";
import {
  INVOICE_STATUS_LABELS,
  PERIOD_KIND_LABELS,
  STATE_LABELS,
  periodLabel,
  schoolSubscription,
  type InvoiceSummary,
  type PeriodMonths,
  type SchoolSubscription,
  type SubscriptionState,
} from "@/lib/subscriptions/client";

const STATE_STYLES: Record<SubscriptionState, string> = {
  NONE: "border-slate-200 bg-slate-50 text-slate-700",
  SCHEDULED: "border-sky-200 bg-sky-50 text-sky-800",
  TRIAL: "border-emerald-200 bg-emerald-50 text-emerald-800",
  ACTIVE: "border-emerald-200 bg-emerald-50 text-emerald-800",
  EXPIRING_SOON: "border-amber-200 bg-amber-50 text-amber-800",
  EXPIRED: "border-red-200 bg-red-50 text-red-800",
};

type Data = { subscription: SchoolSubscription; invoices: InvoiceSummary[] };

// Phase 29, lot A — abonnement de l'école. Les prix, l'effectif et la tranche viennent TOUJOURS de
// l'API (calcul serveur) : la page n'envoie que la durée choisie. L'état affiché ne bloque rien
// (décision « rappels seulement »). Paiement en ligne Mobile Money : lot B (pas encore disponible).
export default function SubscriptionPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canPay = permissions.includes("subscriptions.pay");
  const [reloadKey, setReloadKey] = useState(0);
  const [choice, setChoice] = useState<{ months: PeriodMonths; key: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, error, isLoading, retry } = useAsyncData<Data>(
    async () => {
      const schoolId = currentSchoolId as string;
      const [subscription, invoices] = await Promise.all([
        schoolSubscription.get(schoolId),
        schoolSubscription.invoices(schoolId),
      ]);
      return { subscription, invoices };
    },
    [currentSchoolId, reloadKey],
    { enabled: Boolean(currentSchoolId) },
  );

  if (!currentSchoolId) {
    return <p className="text-sm text-slate-500">Sélectionnez une école pour voir son abonnement.</p>;
  }

  async function confirmChoice() {
    if (!choice || !currentSchoolId) return;
    setSubmitting(true);
    setActionError(null);
    try {
      // Même clé tant que la confirmation est affichée : un double clic ne crée qu'une facture.
      await schoolSubscription.issueInvoice(currentSchoolId, choice.months, choice.key);
      setChoice(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  // Lot C — reçu PDF d'une facture payée, ouvert dans un nouvel onglet.
  async function openReceipt(invoiceId: string) {
    setActionError(null);
    try {
      window.open(await schoolSubscription.receiptBlobUrl(invoiceId), "_blank", "noopener");
    } catch (err) {
      setActionError(toErrorMessage(err));
    }
  }

  const sub = data?.subscription;
  const canChoose = Boolean(sub && canPay && !sub.open_invoice && (sub.quote_required || sub.grid_available));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Abonnement</h1>
        <p className="text-sm text-slate-600">
          État de l&apos;abonnement EduLinkage de l&apos;école, offres et factures.
        </p>
      </div>

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}

      {sub && (
        <>
          <section className={`rounded border p-4 ${STATE_STYLES[sub.state]}`}>
            <p className="text-lg font-semibold">{STATE_LABELS[sub.state]}</p>
            {sub.current_period && (
              <p className="text-sm">
                {PERIOD_KIND_LABELS[sub.current_period.kind]} du {formatDateFR(sub.current_period.starts_on)} au{" "}
                {formatDateFR(sub.current_period.ends_on)}.
              </p>
            )}
            {sub.covered_until && sub.state !== "EXPIRED" && (
              <p className="text-sm">Couvert jusqu&apos;au {formatDateFR(sub.covered_until)}.</p>
            )}
            {sub.state === "EXPIRED" && sub.covered_until && (
              <p className="text-sm">Dernière période terminée le {formatDateFR(sub.covered_until)}.</p>
            )}
            {sub.next_period_starts_on && (
              <p className="text-sm">Prochaine période à partir du {formatDateFR(sub.next_period_starts_on)}.</p>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Offres</h2>
            <p className="text-sm text-slate-600">
              Effectif actuel : <strong>{sub.active_student_count}</strong> élève
              {sub.active_student_count > 1 ? "s" : ""} actif{sub.active_student_count > 1 ? "s" : ""}
              {sub.tier !== null && <> — tranche {sub.tier === 0 ? "de base" : sub.tier}</>}. L&apos;effectif et le prix
              sont figés sur la facture au moment de l&apos;émission.
            </p>
            {sub.quote_required ? (
              <p className="rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
                Plus de 1 000 élèves actifs : tarif adapté. Choisissez une durée pour demander un devis à EduLinkage.
              </p>
            ) : (
              !sub.grid_available && (
                <p className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
                  Les tarifs ne sont pas encore publiés.
                </p>
              )
            )}
            <div className="grid gap-3 sm:grid-cols-3">
              {sub.offers.map((offer) => (
                <div key={offer.period_months} className="flex flex-col gap-2 rounded border border-slate-200 bg-white p-4">
                  <p className="font-medium text-slate-900">{periodLabel(offer.period_months)}</p>
                  <p className="text-xl font-semibold text-slate-900">
                    {offer.total_amount ? formatApiAmount(offer.total_amount, sub.currency) : sub.quote_required ? "Sur devis" : "—"}
                  </p>
                  {offer.total_amount && offer.supplement_amount && Number(offer.supplement_amount) > 0 && (
                    <p className="text-xs text-slate-500">
                      Forfait de base {formatApiAmount(offer.base_amount ?? "0", sub.currency)} + supplément{" "}
                      {formatApiAmount(offer.supplement_amount, sub.currency)}
                    </p>
                  )}
                  {canChoose && (offer.total_amount || sub.quote_required) && (
                    <button
                      type="button"
                      onClick={() => {
                        setActionError(null);
                        setChoice({ months: offer.period_months, key: schoolSubscription.newIdempotencyKey() });
                      }}
                      className="mt-auto rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
                    >
                      {sub.quote_required ? "Demander un devis" : sub.state === "NONE" ? "S'abonner" : "Renouveler"}
                    </button>
                  )}
                </div>
              ))}
            </div>
            {!canPay && (
              <p className="text-xs text-slate-500">Seul l&apos;administrateur de l&apos;école peut émettre une facture.</p>
            )}
          </section>

          {choice && (
            <section className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4">
              <p className="text-sm text-slate-800">
                Confirmer {sub.quote_required ? "la demande de devis" : "l'émission de la facture"} pour{" "}
                <strong>{periodLabel(choice.months)}</strong> ? L&apos;effectif de {sub.active_student_count} élève
                {sub.active_student_count > 1 ? "s" : ""} actif{sub.active_student_count > 1 ? "s" : ""} et le prix seront figés.
              </p>
              {actionError && <p className="text-sm text-red-700">{actionError}</p>}
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={confirmChoice}
                  className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {submitting ? "Émission..." : "Confirmer"}
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setChoice(null)}
                  className="rounded border border-slate-300 px-3 py-2 text-sm"
                >
                  Annuler
                </button>
              </div>
            </section>
          )}

          {sub.open_invoice && (
            <section className="flex flex-col gap-2 rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">
                {sub.open_invoice.status === "QUOTE_REQUIRED"
                  ? "Demande de devis en cours"
                  : `Facture ${sub.open_invoice.number} à payer`}
              </p>
              {sub.open_invoice.total_amount && (
                <p>
                  Montant : <strong>{formatApiAmount(sub.open_invoice.total_amount, sub.open_invoice.currency)}</strong> pour{" "}
                  {periodLabel(sub.open_invoice.period_months)} — valable jusqu&apos;au{" "}
                  {sub.open_invoice.expires_at ? formatDateFR(sub.open_invoice.expires_at) : "—"}.
                </p>
              )}
              <p>
                Le paiement en ligne par Mobile Money arrive prochainement. En attendant, contactez EduLinkage pour le
                règlement en indiquant le numéro de facture : le paiement sera enregistré par EduLinkage.
              </p>
            </section>
          )}

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold text-slate-900">Factures</h2>
            {actionError && !choice && <p className="text-sm text-red-700">{actionError}</p>}
            {data.invoices.length === 0 ? (
              <p className="text-sm text-slate-500">Aucune facture.</p>
            ) : (
              <div className="overflow-x-auto rounded border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      {["Numéro", "Durée", "Effectif", "Montant", "Statut", "Émise le", "Reçu"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-medium text-slate-600">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td className="px-3 py-2">{invoice.number ?? "Devis"}</td>
                        <td className="px-3 py-2">{invoice.period_months} mois</td>
                        <td className="px-3 py-2">{invoice.student_count}</td>
                        <td className="px-3 py-2">
                          {invoice.total_amount ? formatApiAmount(invoice.total_amount, invoice.currency) : "—"}
                        </td>
                        <td className="px-3 py-2">{INVOICE_STATUS_LABELS[invoice.status]}</td>
                        <td className="px-3 py-2">{invoice.issued_at ? formatDateFR(invoice.issued_at) : "—"}</td>
                        <td className="px-3 py-2">
                          {invoice.status === "PAID" ? (
                            <button type="button" onClick={() => openReceipt(invoice.id)} className="text-sky-700 underline">
                              Télécharger
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {sub.periods.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="text-lg font-semibold text-slate-900">Périodes</h2>
              <ul className="flex flex-col gap-1 text-sm text-slate-700">
                {sub.periods.map((period) => (
                  <li key={period.id}>
                    {PERIOD_KIND_LABELS[period.kind]} : du {formatDateFR(period.starts_on)} au {formatDateFR(period.ends_on)}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
