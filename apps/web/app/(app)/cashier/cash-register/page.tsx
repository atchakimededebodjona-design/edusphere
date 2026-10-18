"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CashCountAndClose } from "@/components/cash/CashCountAndClose";
import { CashMovementsSection } from "@/components/cash/CashMovementsSection";
import { CashSessionList } from "@/components/cash/CashSessionList";
import { CashTotalsCard } from "@/components/cash/CashTotalsCard";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { cashRegister, type CashRegisterContext, type CashSessionSummary } from "@/lib/cash/client";
import { cashErrorMessage } from "@/lib/cash/errors";
import { formatApiAmount, toCents, centsToApi } from "@/lib/fees/allocation";
import { PAYMENT_STATUS_LABELS } from "@/lib/fees/labels";
import { formatDateFR } from "@/lib/format/date";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// Caisse scolaire, lot 3 — "Ma caisse" : ouverture, encaissements, mouvements, solde théorique,
// comptage par coupure, écart/justification, clôture, historique. Affichée avec
// `cash.register.read` (lisibilité) ; chaque opération est autorisée et validée par l'API.
export default function CashRegisterPage() {
  const { currentSchoolId, permissions, user } = useAuth();
  const canRead = permissions.includes("cash.register.read");
  const canManage = permissions.includes("cash.register.manage");

  const [context, setContext] = useState<CashRegisterContext | null>(null);
  const [history, setHistory] = useState<CashSessionSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opening, setOpening] = useState("");
  const [openError, setOpenError] = useState<string | null>(null);
  const [isOpening, setIsOpening] = useState(false);
  const [justClosed, setJustClosed] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!currentSchoolId || !user) return;
    setLoadError(null);
    try {
      const [ctx, sessions] = await Promise.all([
        cashRegister.current(currentSchoolId),
        cashRegister.list(currentSchoolId, { cashierUserId: user.id }),
      ]);
      setContext(ctx);
      setHistory(sessions);
    } catch (err) {
      setLoadError(toErrorMessage(err));
    }
  }, [currentSchoolId, user]);

  useEffect(() => {
    if (canRead) void reload();
  }, [canRead, reload]);

  async function openSession() {
    const cents = toCents(opening.trim() === "" ? "0" : opening);
    if (!currentSchoolId || cents === null || isOpening) return;
    setIsOpening(true);
    setOpenError(null);
    try {
      await cashRegister.open(currentSchoolId, centsToApi(cents));
      setOpening("");
      setJustClosed(null);
      await reload();
    } catch (err) {
      setOpenError(cashErrorMessage(err));
    } finally {
      setIsOpening(false);
    }
  }

  async function afterChange() {
    const previous = context?.current?.session.id ?? null;
    await reload();
    setJustClosed(previous);
  }

  if (!canRead) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Ma caisse</h1>
        <p role="alert" className="rounded border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          Cet espace est réservé aux comptes disposant d&apos;une caisse.
        </p>
      </div>
    );
  }
  if (loadError) return <ErrorRetry message={loadError} onRetry={() => void reload()} />;
  if (!context || history === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  const current = context.current;
  const currency = context.currency;
  const closedSession = !current && justClosed ? history.find((s) => s.id === justClosed) ?? null : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-bold text-slate-900">Ma caisse</h1>
        <p className="text-sm text-slate-600">
          Journée du {formatDateFR(context.business_date)} ({context.timezone})
        </p>
      </div>

      {current ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-4">
            <section
              aria-label="État de ma caisse"
              className="flex flex-wrap items-center justify-between gap-3 rounded border border-emerald-300 bg-emerald-50 p-4"
            >
              <div>
                <p data-testid="cash-session-status" className="text-lg font-bold text-emerald-900">
                  Caisse ouverte
                </p>
                <p className="text-sm text-emerald-900">
                  Depuis {formatTime(current.session.opened_at)} · Fonds initial{" "}
                  {formatApiAmount(current.session.opening_amount, currency)}
                </p>
              </div>
              <Link href="/cashier" className="rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">
                Encaisser un élève
              </Link>
            </section>

            <section aria-labelledby="cash-payments-title" className="rounded border border-slate-200 bg-white p-4">
              <h2 id="cash-payments-title" className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600">
                Encaissements de la session
              </h2>
              {current.payments.length === 0 ? (
                <p className="text-sm text-slate-500">Aucun encaissement dans cette session.</p>
              ) : (
                <ul aria-label="Encaissements de la session" className="divide-y divide-slate-100 text-sm">
                  {current.payments.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">
                          {p.receipt_number}
                          <span className="ml-2 text-xs font-normal text-slate-500">{formatTime(p.created_at)}</span>
                        </p>
                        <p className="truncate text-xs text-slate-600">
                          {p.student_last_name} {p.student_first_name} · {p.student_matricule}
                        </p>
                      </div>
                      <span className={p.status === "CANCELLED" ? "text-slate-400 line-through" : "font-semibold"}>
                        {formatApiAmount(p.amount, currency)}
                        {p.status === "CANCELLED" && <span className="ml-1 text-xs no-underline">({PAYMENT_STATUS_LABELS[p.status]})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <CashMovementsSection
              sessionId={current.session.id}
              movements={current.movements}
              currency={currency}
              canManage={canManage}
              onChanged={() => void reload()}
            />
          </div>

          <div className="flex min-w-0 flex-col gap-4">
            <CashTotalsCard totals={current.totals} currency={currency} />
            {canManage && (
              <CashCountAndClose
                key={`${current.session.id}-${current.latest_count?.id ?? "none"}`}
                sessionId={current.session.id}
                currency={currency}
                denominations={context.denominations}
                varianceReasons={context.variance_reasons}
                expectedAmount={current.totals.expected_amount}
                latestCount={current.latest_count}
                onChanged={() => void afterChange()}
              />
            )}
          </div>
        </div>
      ) : (
        <section aria-label="État de ma caisse" className="flex flex-col gap-3 rounded border border-slate-200 bg-white p-4">
          {closedSession && (
            <p
              data-testid="cash-closed-banner"
              className="rounded border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            >
              Caisse clôturée : théorique {formatApiAmount(closedSession.expected_amount ?? "0", currency)}, physique{" "}
              {formatApiAmount(closedSession.counted_amount ?? "0", currency)}, écart{" "}
              {formatApiAmount(closedSession.variance_amount ?? "0", currency)}.
            </p>
          )}
          <p data-testid="cash-session-status" className="text-lg font-bold text-slate-900">
            Aucune caisse ouverte
          </p>
          {canManage ? (
            <form
              aria-label="Ouvrir ma caisse"
              onSubmit={(e) => {
                e.preventDefault();
                void openSession();
              }}
              className="flex flex-col gap-2 sm:flex-row sm:items-end"
            >
              <label className="flex flex-col gap-1 text-sm text-slate-700">
                Fonds de caisse initial
                <input
                  value={opening}
                  onChange={(e) => setOpening(e.target.value)}
                  inputMode="decimal"
                  placeholder="0"
                  className="rounded border border-slate-300 px-3 py-2 text-lg font-semibold"
                />
              </label>
              <button
                type="submit"
                disabled={isOpening || toCents(opening.trim() === "" ? "0" : opening) === null}
                className="rounded bg-emerald-700 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-40"
              >
                {isOpening ? "Ouverture..." : "Ouvrir ma caisse"}
              </button>
            </form>
          ) : (
            <p className="text-sm text-slate-600">Vous n&apos;êtes pas autorisé à ouvrir une caisse.</p>
          )}
          {openError && (
            <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {openError}
            </p>
          )}
        </section>
      )}

      <section aria-labelledby="cash-history-title" className="flex flex-col gap-2">
        <h2 id="cash-history-title" className="text-lg font-semibold text-slate-900">
          Historique de mes caisses
        </h2>
        <CashSessionList sessions={history} currency={currency} showCashier={false} label="Historique de mes caisses" />
      </section>
    </div>
  );
}
