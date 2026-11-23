"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CashierDayHistory } from "@/components/cashier/CashierDayHistory";
import { CashierStudentSearch } from "@/components/cashier/CashierStudentSearch";
import { CashPaymentForm, type OfflineCollection } from "@/components/cashier/CashPaymentForm";
import { ProvisionalReceiptCard, printProvisionalReceipt } from "@/components/cashier/ProvisionalReceipt";
import { openReceipt } from "@/components/cashier/receipt";
import { OutboxFailures } from "@/components/pwa/OutboxFailures";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { offlineSummary, withPendingPayments } from "@/lib/cashier/offline";
import { cashRegister } from "@/lib/cash/client";
import { formatApiAmount, localIsoDate } from "@/lib/fees/allocation";
import {
  cashier,
  financialSummary,
  type CashierDay,
  type CashierRoster,
  type CashierStudent,
  type FinancialSummary,
  type Payment,
} from "@/lib/fees/client";
import { formatDateFR } from "@/lib/format/date";
import { useServerReachable } from "@/lib/offline/connectivity";
import {
  isPaymentEntry,
  OUTBOX_CHANGED_EVENT,
  type OutboxChange,
  type ProvisionalReceipt,
} from "@/lib/offline/outbox";
import { useOutbox } from "@/lib/offline/useOutbox";

type Recorded = { payment: Payment; student: CashierStudent; newBalance: string | null };

// Phase 32, lot 3 — liste des élèves gardée sur l'appareil, rafraîchie tant que la page est ouverte.
const ROSTER_REFRESH_MS = 10 * 60 * 1000;

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return `${date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })} à ${date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

// Pas de réponse du serveur : appareil hors ligne, aucune copie, ou passerelle sans API.
function serverUnreachable(err: unknown): boolean {
  return !(err instanceof ApiError) || err.status === 0 || err.status === 502 || err.status === 503 || err.status === 504;
}

// Caisse scolaire, lot 2 — poste d'encaissement en espèces. Affiché seulement avec
// `payments.manage` (lisibilité) ; l'API reste la seule autorité : CASH imposé au CAISSIER,
// isolation école/organisation, idempotence et plafonnement au solde sont tous vérifiés côté
// backend (fees/router.py, fees/service.py, cashier/router.py).
//
// Phase 32, lot 3 — sans internet, caisse ouverte : recherche dans la liste gardée sur l'appareil,
// encaissement gardé puis envoyé au retour du réseau, reçu provisoire remis au payeur.
export default function CashierPage() {
  const { currentSchoolId, currentSchool, permissions, user } = useAuth();
  const canCollect = permissions.includes("payments.manage");
  const reachable = useServerReachable();
  const outbox = useOutbox();
  const unsent = useMemo(
    () => outbox.filter(isPaymentEntry).filter((entry) => entry.schoolId === currentSchoolId),
    [outbox, currentSchoolId],
  );

  const [day, setDay] = useState<CashierDay | null>(null);
  const [dayError, setDayError] = useState<string | null>(null);
  const [student, setStudent] = useState<CashierStudent | null>(null);
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<Recorded | null>(null);
  const [receiptError, setReceiptError] = useState<string | null>(null);
  const [provisional, setProvisional] = useState<{ receipt: ProvisionalReceipt; key: string; justCollected: boolean } | null>(
    null,
  );
  const [roster, setRoster] = useState<CashierRoster | null>(null);
  // Encaissements gardés puis acceptés par le serveur : cible -> paiement créé (reçu officiel).
  const [sentPayments, setSentPayments] = useState<Record<string, string>>({});
  useEffect(() => {
    const onChange = (event: Event) => {
      const { sentKey, targetId } = (event as CustomEvent<OutboxChange>).detail ?? {};
      if (sentKey?.startsWith("payment:") && targetId) setSentPayments((prev) => ({ ...prev, [sentKey]: targetId }));
    };
    window.addEventListener(OUTBOX_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(OUTBOX_CHANGED_EVENT, onChange);
  }, []);

  const loadDay = useCallback(async (schoolId: string) => {
    setDayError(null);
    try {
      setDay(await cashier.myDay(schoolId, localIsoDate()));
    } catch (err) {
      setDayError(toErrorMessage(err));
    }
  }, []);

  const loadSummary = useCallback(
    async (studentId: string) => {
      setSummary(null);
      setSummaryError(null);
      const offlineFallback = async (err: unknown) => {
        const copy = await offlineSummary(studentId, roster);
        if (copy) setSummary(withPendingPayments(copy, unsent));
        else
          setSummaryError(
            err === null
              ? "Sans internet : la situation de cet élève n'est pas gardée sur cet appareil."
              : toErrorMessage(err),
          );
      };
      if (!reachable) {
        await offlineFallback(null);
        return;
      }
      try {
        setSummary(withPendingPayments(await financialSummary.get(studentId), unsent));
      } catch (err) {
        if (serverUnreachable(err)) await offlineFallback(err);
        else setSummaryError(toErrorMessage(err));
      }
    },
    [reachable, roster, unsent],
  );

  useEffect(() => {
    if (canCollect && currentSchoolId) void loadDay(currentSchoolId);
  }, [canCollect, currentSchoolId, loadDay]);

  // Encaissement gardé envoyé (ou refusé) : le journal du jour est relu.
  const unsentCount = unsent.length;
  useEffect(() => {
    if (canCollect && currentSchoolId && reachable) void loadDay(currentSchoolId);
  }, [canCollect, currentSchoolId, reachable, unsentCount, loadDay]);

  // Lot 3 — état de la caisse (session) de l'utilisateur : un CAISSIER n'encaisse des espèces que
  // dans sa caisse OUVERTE (imposé par l'API ; ce bandeau ne fait que l'annoncer). Hors connexion,
  // la copie gardée sur l'appareil donne la caisse ouverte en dernier.
  const canSeeRegister = permissions.includes("cash.register.read");
  const [registerSessionId, setRegisterSessionId] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (!canSeeRegister || !currentSchoolId) return;
    cashRegister
      .current(currentSchoolId)
      .then((ctx) => setRegisterSessionId(ctx.current?.session.id ?? null))
      .catch(() => setRegisterSessionId(undefined));
  }, [canSeeRegister, currentSchoolId, reachable]);
  const registerOpen = registerSessionId === undefined ? null : registerSessionId !== null;

  // Phase 32, lot 3 — liste des élèves gardée sur l'appareil, seulement caisse ouverte (l'API refuse
  // sinon). Relue depuis la copie de l'appareil hors connexion.
  useEffect(() => {
    if (!canCollect || !currentSchoolId || !registerSessionId) {
      setRoster(null);
      return;
    }
    let cancelled = false;
    const load = () =>
      cashier
        .offlineRoster(currentSchoolId)
        .then((list) => {
          if (!cancelled) setRoster(list);
        })
        .catch(() => {
          // Pas de liste (aucune copie, caisse fermée entre-temps) : la recherche en ligne reste.
        });
    void load();
    const id = window.setInterval(() => void load(), ROSTER_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [canCollect, currentSchoolId, registerSessionId, reachable]);

  const offlineCollection: OfflineCollection | null =
    currentSchoolId && registerSessionId
      ? {
          schoolId: currentSchoolId,
          schoolName: currentSchool?.name ?? "",
          cashSessionId: registerSessionId,
          cashierName: user?.full_name ?? null,
        }
      : null;

  // Changement d'école : on repart d'un poste vierge (aucun élève d'une autre école conservé).
  useEffect(() => {
    setStudent(null);
    setSummary(null);
    setRecorded(null);
    setProvisional(null);
  }, [currentSchoolId]);

  function selectStudent(selected: CashierStudent) {
    setRecorded(null);
    setProvisional(null);
    setStudent(selected);
    void loadSummary(selected.id);
  }

  function resetDesk() {
    setRecorded(null);
    setProvisional(null);
    setStudent(null);
    setSummary(null);
    setSummaryError(null);
    setReceiptError(null);
  }

  async function handleRecorded(payment: Payment) {
    if (!student) return;
    setRecorded({ payment, student, newBalance: null });
    if (currentSchoolId) void loadDay(currentSchoolId);
    try {
      const refreshed = await financialSummary.get(student.id);
      setSummary(refreshed);
      setRecorded({ payment, student, newBalance: refreshed.balance });
    } catch {
      // Le paiement est enregistré (201) : un échec de relecture du solde n'annule rien, le
      // nouveau solde reste simplement non affiché (il figure aussi sur le reçu).
    }
  }

  function handleQueued(receipt: ProvisionalReceipt, key: string) {
    setRecorded(null);
    setProvisional({ receipt, key, justCollected: true });
  }

  // État réel de l'encaissement dont le reçu provisoire est affiché.
  const provisionalEntry = provisional ? unsent.find((entry) => entry.key === provisional.key) ?? null : null;
  const sentPaymentId = provisional ? sentPayments[provisional.key] ?? null : null;
  const officialPayment = sentPaymentId ? day?.payments.find((p) => p.id === sentPaymentId) ?? null : null;
  const provisionalState: "sent" | "failed" | "pending" =
    provisionalEntry?.state === "failed" ? "failed" : sentPaymentId && !provisionalEntry ? "sent" : "pending";

  async function handleReceipt(paymentId: string) {
    setReceiptError(null);
    try {
      await openReceipt(paymentId);
    } catch (err) {
      setReceiptError(toErrorMessage(err));
    }
  }

  if (!canCollect) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Caisse scolaire</h1>
        <p role="alert" className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          Cet espace est réservé aux comptes autorisés à enregistrer des paiements.
        </p>
      </div>
    );
  }

  if (!currentSchoolId) {
    return <p className="text-sm text-slate-600">Chargement...</p>;
  }

  const currency = day?.currency ?? roster?.currency ?? currentSchool?.currency ?? "";

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Caisse scolaire</h1>
      {registerOpen === false && (
        <p
          data-testid="cash-register-closed-banner"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <span>Aucune caisse ouverte : ouvrez votre caisse avant d&apos;encaisser des espèces.</span>
          <Link href="/cashier/cash-register" className="inline-flex min-h-10 items-center rounded-lg bg-amber-800 px-4 text-sm font-semibold text-white hover:bg-amber-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600">
            Ouvrir ma caisse
          </Link>
        </p>
      )}
      {!reachable && (
        <p
          data-testid="cash-offline-notice"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          {offlineCollection && roster
            ? `Sans internet : les encaissements sont gardés sur cet appareil avec un reçu provisoire, et partiront au retour d'internet. Liste des élèves du ${formatDateTime(roster.generated_at)}.`
            : "Sans internet : encaisser n'est possible que si votre caisse a été ouverte avec internet sur cet appareil (la page Caisse ouverte au moins une fois, caisse ouverte)."}
        </p>
      )}

      <OutboxFailures kind="payment" />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {provisional ? (
            <section
              aria-labelledby="cash-provisional-title"
              className={`flex flex-col gap-4 rounded-lg border p-4 ${
                provisionalState === "failed"
                  ? "border-red-300 bg-red-50"
                  : provisionalState === "sent"
                    ? "border-emerald-300 bg-emerald-50"
                    : "border-sky-300 bg-sky-50"
              }`}
            >
              <h2 id="cash-provisional-title" className="text-xl font-bold text-slate-900">
                {provisionalState === "failed"
                  ? "Encaissement refusé par le serveur"
                  : provisionalState === "sent"
                    ? "Encaissement envoyé au serveur"
                    : provisional.justCollected
                      ? "Encaissement gardé sur cet appareil"
                      : "Reçu provisoire — en attente d'envoi"}
              </h2>
              {provisionalState === "pending" && provisional.justCollected && (
                <p className="text-sm text-sky-900">
                  Le serveur ne répond pas : l&apos;encaissement partira automatiquement au retour d&apos;internet et
                  recevra alors son numéro de reçu officiel. Remettez au payeur le reçu provisoire ci-dessous.
                </p>
              )}
              {provisionalState === "failed" && (
                <p className="text-sm text-red-800">
                  {provisionalEntry?.error} Le paiement n&apos;est pas enregistré : voir la régularisation en haut de page.
                </p>
              )}
              {provisionalState === "sent" && sentPaymentId && (
                <p data-testid="cash-provisional-sent" className="text-sm text-emerald-900">
                  {officialPayment
                    ? `Reçu officiel ${officialPayment.receipt_number} : il remplace le reçu provisoire ${provisional.receipt.number}.`
                    : `Enregistré par le serveur : le reçu officiel remplace le reçu provisoire ${provisional.receipt.number}.`}{" "}
                  <button type="button" onClick={() => void handleReceipt(sentPaymentId)} className="font-medium underline">
                    Voir le reçu officiel
                  </button>
                </p>
              )}
              {receiptError && provisionalState === "sent" && (
                <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {receiptError}
                </p>
              )}
              <ProvisionalReceiptCard receipt={provisional.receipt} />
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={printProvisionalReceipt}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                >
                  Imprimer le reçu provisoire
                </button>
                <button
                  type="button"
                  onClick={resetDesk}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                >
                  Nouvel encaissement
                </button>
              </div>
            </section>
          ) : recorded ? (
            <section
              aria-labelledby="cash-success-title"
              className="flex flex-col gap-4 rounded-xl border border-emerald-300 bg-emerald-50 p-4"
            >
              <h2 id="cash-success-title" className="text-xl font-bold text-emerald-900">
                Encaissement enregistré
              </h2>
              <dl className="grid gap-2 text-sm sm:grid-cols-[max-content_1fr] sm:gap-x-6">
                <dt className="text-emerald-800">Numéro de reçu</dt>
                <dd data-testid="cash-receipt-number" className="text-lg font-bold text-slate-900">
                  {recorded.payment.receipt_number}
                </dd>
                <dt className="text-emerald-800">Montant</dt>
                <dd className="text-lg font-bold text-slate-900">{formatApiAmount(recorded.payment.amount, currency)}</dd>
                <dt className="text-emerald-800">Élève</dt>
                <dd className="text-slate-900">
                  {recorded.student.last_name} {recorded.student.first_name} ({recorded.student.matricule})
                </dd>
                <dt className="text-emerald-800">Date</dt>
                <dd className="text-slate-900">{formatDateFR(recorded.payment.paid_at)}</dd>
                <dt className="text-emerald-800">Caissier</dt>
                <dd className="text-slate-900">{user?.full_name ?? "—"}</dd>
                <dt className="text-emerald-800">Nouveau solde</dt>
                <dd data-testid="cash-new-balance" className="font-semibold text-slate-900">
                  {recorded.newBalance === null ? "—" : formatApiAmount(recorded.newBalance, currency)}
                </dd>
              </dl>
              {receiptError && (
                <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {receiptError}
                </p>
              )}
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => void handleReceipt(recorded.payment.id)}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                >
                  Voir le reçu
                </button>
                <button
                  type="button"
                  onClick={resetDesk}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                >
                  Nouvel encaissement
                </button>
              </div>
            </section>
          ) : student ? (
            <>
              <section
                aria-label="Élève sélectionné"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4"
              >
                <div>
                  <p data-testid="cash-selected-student" className="text-lg font-semibold text-slate-900">
                    {student.last_name} {student.first_name}
                  </p>
                  <p className="text-sm text-slate-600">
                    Matricule : {student.matricule} · Classe : {student.current_class_name ?? "non renseignée"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={resetDesk}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                >
                  Changer d&apos;élève
                </button>
              </section>
              {summaryError && <ErrorRetry message={summaryError} onRetry={() => void loadSummary(student.id)} />}
              {!summary && !summaryError && <p className="text-sm text-slate-600">Chargement de la situation...</p>}
              {summary && (
                <CashPaymentForm
                  key={student.id}
                  student={student}
                  summary={summary}
                  currency={currency}
                  onRecorded={(payment) => void handleRecorded(payment)}
                  offline={offlineCollection}
                  onQueued={handleQueued}
                />
              )}
            </>
          ) : (
            <CashierStudentSearch
              schoolId={currentSchoolId}
              onSelect={selectStudent}
              roster={roster}
              offline={!reachable}
            />
          )}
        </div>

        <aside className="min-w-0">
          <CashierDayHistory
            day={day}
            error={dayError}
            onRetry={() => void loadDay(currentSchoolId)}
            unsent={unsent}
            currency={currency}
            onShowProvisional={(entry) => {
              setRecorded(null);
              setProvisional({ receipt: entry.receipt, key: entry.key, justCollected: false });
            }}
          />
        </aside>
      </div>
    </div>
  );
}
