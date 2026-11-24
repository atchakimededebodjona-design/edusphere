"use client";

import { useEffect, useState, type FormEvent } from "react";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { formatApiAmount } from "@/lib/fees/allocation";
import {
  IN_PROGRESS_PAYMENT_STATUSES,
  NETWORK_LABELS,
  schoolSubscription,
  type InvoiceSummary,
  type OnlineNetwork,
  type OnlinePayment,
} from "@/lib/subscriptions/client";

const POLL_INTERVAL_MS = 5000;
// 3 minutes de vérification automatique ; au-delà, un bouton permet de relancer la vérification
// (le serveur continue de toute façon : notification PayGate et tâche de rapprochement).
const MAX_AUTOMATIC_POLLS = 36;

type Props = {
  invoice: InvoiceSummary;
  maxAmount: number;
  onPaid: () => void;
};

function isInProgress(payment: OnlinePayment | null): boolean {
  return Boolean(payment && IN_PROGRESS_PAYMENT_STATUSES.includes(payment.status));
}

// Phase 29, lot B — paiement Mobile Money d'une facture émise (PayGate Global, méthode directe).
// La page n'envoie que le réseau et le numéro : le montant est celui de la facture, fixé par le
// serveur. Le paiement n'est réputé fait QUE lorsque le serveur l'a vérifié auprès de PayGate.
export function OnlinePaymentPanel({ invoice, maxAmount, onPaid }: Props) {
  const [network, setNetwork] = useState<OnlineNetwork>("FLOOZ");
  const [phone, setPhone] = useState("");
  const [paymentKey, setPaymentKey] = useState(() => schoolSubscription.newPaymentKey());
  const [attempt, setAttempt] = useState<OnlinePayment | null>(null);
  const [polls, setPolls] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Une tentative peut déjà être en cours (page rechargée, autre onglet) : on la reprend.
  useEffect(() => {
    let cancelled = false;
    schoolSubscription
      .invoice(invoice.id)
      .then((detail) => {
        const inProgress = detail.payments.filter(
          (payment) => payment.provider === "PAYGATE" && IN_PROGRESS_PAYMENT_STATUSES.includes(payment.status),
        );
        const current = inProgress[inProgress.length - 1];
        if (!cancelled && current) {
          setAttempt({ ...current, invoice_id: invoice.id, method: current.method as OnlineNetwork });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [invoice.id]);

  useEffect(() => {
    if (!attempt || !isInProgress(attempt) || polls >= MAX_AUTOMATIC_POLLS) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await schoolSubscription.onlinePayment(attempt.id);
        setAttempt(next);
        if (next.status === "SUCCEEDED") onPaid();
      } catch (err) {
        setError(toErrorMessage(err));
      } finally {
        setPolls((count) => count + 1);
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [attempt, polls, onPaid]);

  if (invoice.total_amount && Number(invoice.total_amount) > maxAmount) {
    return (
      <p>
        Le montant de cette facture dépasse le plafond du paiement en ligne. Contactez EduLinkage en indiquant le numéro de
        facture : le paiement sera enregistré par EduLinkage.
      </p>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    // Après une tentative close (échec, sans confirmation), une nouvelle clé : la même clé
    // renverrait la tentative précédente (idempotence côté serveur).
    const key = attempt ? schoolSubscription.newPaymentKey() : paymentKey;
    setPaymentKey(key);
    setSubmitting(true);
    setError(null);
    try {
      const result = await schoolSubscription.startOnlinePayment(invoice.id, network, phone, key);
      setAttempt(result);
      setPolls(0);
      if (result.status === "SUCCEEDED") onPaid();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (attempt && isInProgress(attempt)) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sky-900">
        <p className="font-semibold">Paiement en attente de confirmation</p>
        <p>
          Une demande de paiement de {formatApiAmount(attempt.amount, attempt.currency)} a été envoyée au numéro{" "}
          {NETWORK_LABELS[attempt.method]} se terminant par <strong>{attempt.payer_phone_last4 ?? "—"}</strong>. Validez-la
          sur ce téléphone avec votre code secret.
        </p>
        {polls < MAX_AUTOMATIC_POLLS ? (
          <p className="text-sm">Vérification automatique en cours… Ne relancez pas un second paiement.</p>
        ) : (
          <div className="flex flex-col gap-2 text-sm">
            <p>
              Pas encore de confirmation. Si vous avez validé le paiement, la vérification continue côté EduLinkage ; vous
              pouvez aussi vérifier maintenant.
            </p>
            <button
              type="button"
              onClick={() => setPolls(MAX_AUTOMATIC_POLLS - 1)}
              className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 self-start"
            >
              Vérifier maintenant
            </button>
          </div>
        )}
        {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      </div>
    );
  }

  if (attempt?.status === "SUCCEEDED") {
    return <p className="font-semibold text-emerald-800">Paiement confirmé. Merci !</p>;
  }

  if (attempt?.status === "ANOMALY") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-800">
        Votre paiement a été reçu mais doit être vérifié par EduLinkage. Ne payez pas une seconde fois : EduLinkage vous
        contactera.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {attempt && (attempt.status === "FAILED" || attempt.status === "EXPIRED") && (
        <p className="rounded-lg border border-amber-300 bg-white p-3 text-amber-900">
          Le paiement précédent n&apos;a pas abouti (refusé, annulé ou non validé à temps). Aucun montant n&apos;a été
          enregistré : vous pouvez réessayer.
        </p>
      )}
      <p className="font-medium">Payer par Mobile Money</p>
      <div className="flex flex-wrap gap-4">
        {(Object.keys(NETWORK_LABELS) as OnlineNetwork[]).map((code) => (
          <label key={code} className="flex items-center gap-2">
            <input type="radio" name="network" value={code} checked={network === code} onChange={() => setNetwork(code)} />
            {NETWORK_LABELS[code]}
          </label>
        ))}
      </div>
      <label className="flex flex-col gap-1">
        Numéro qui paiera (Togo, 8 chiffres)
        <input
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          required
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="90 12 34 56"
          className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 max-w-xs"
        />
      </label>
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <button
        type="submit"
        disabled={submitting || phone.trim().length < 8}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 self-start"
      >
        {submitting ? "Envoi de la demande..." : `Payer ${invoice.total_amount ? formatApiAmount(invoice.total_amount, invoice.currency) : ""}`}
      </button>
      <p className="text-xs">
        Vous recevrez sur ce téléphone une demande de confirmation de l&apos;opérateur. Le paiement n&apos;est pris en compte
        qu&apos;après sa vérification par EduLinkage auprès de PayGate.
      </p>
    </form>
  );
}
