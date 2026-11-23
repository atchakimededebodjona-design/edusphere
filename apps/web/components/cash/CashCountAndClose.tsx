"use client";

import { useState } from "react";
import { cashRegister, type CashCount, type CashVarianceReason } from "@/lib/cash/client";
import { cashErrorMessage } from "@/lib/cash/errors";
import { CASH_VARIANCE_REASON_LABELS } from "@/lib/cash/labels";
import { formatApiAmount, formatMoney, toCents } from "@/lib/fees/allocation";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

/** Comptage par coupure, écart, justification et clôture. Le total officiel du comptage et l'écart
 * sont calculés par l'API ; l'aperçu local ne sert qu'à la saisie. La clôture renvoie le comptage
 * et le solde théorique AFFICHÉS : l'API refuse (409) si l'un des deux a changé entre-temps. */
export function CashCountAndClose({
  sessionId,
  currency,
  denominations,
  varianceReasons,
  expectedAmount,
  latestCount,
  onChanged,
}: {
  sessionId: string;
  currency: string;
  denominations: string[];
  varianceReasons: CashVarianceReason[];
  expectedAmount: string;
  latestCount: CashCount | null;
  onChanged: () => void;
}) {
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [countError, setCountError] = useState<string | null>(null);
  const [isCounting, setIsCounting] = useState(false);
  const [reason, setReason] = useState<CashVarianceReason | "">("");
  const [note, setNote] = useState("");
  const [closeError, setCloseError] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);

  const parsed = denominations.map((denomination) => {
    const raw = (quantities[denomination] ?? "").trim();
    const quantity = raw === "" ? 0 : /^\d+$/.test(raw) ? Number(raw) : null;
    return { denomination, quantity };
  });
  const invalid = parsed.some((line) => line.quantity === null);
  const previewCents = invalid
    ? null
    : parsed.reduce((sum, line) => sum + (toCents(line.denomination) ?? 0) * (line.quantity ?? 0), 0);

  const expectedCents = toCents(expectedAmount) ?? 0;
  const countedCents = latestCount ? toCents(latestCount.total_amount) ?? 0 : null;
  const varianceCents = countedCents === null ? null : countedCents - expectedCents;
  const needsJustification = varianceCents !== null && varianceCents !== 0;
  const canClose =
    latestCount !== null && !isClosing && (!needsJustification || (reason !== "" && note.trim().length > 0));

  async function submitCount() {
    if (invalid || isCounting) return;
    const lines = parsed.filter((line) => (line.quantity ?? 0) > 0) as { denomination: string; quantity: number }[];
    setIsCounting(true);
    setCountError(null);
    try {
      // Caisse vide : un comptage explicite à zéro reste un comptage (jamais une absence de comptage).
      await cashRegister.count(sessionId, lines.length > 0 ? lines : [{ denomination: denominations[0], quantity: 0 }]);
      setQuantities({});
      onChanged();
    } catch (err) {
      setCountError(cashErrorMessage(err));
    } finally {
      setIsCounting(false);
    }
  }

  async function submitClose() {
    if (!canClose || !latestCount) return;
    setIsClosing(true);
    setCloseError(null);
    try {
      await cashRegister.close(sessionId, {
        count_id: latestCount.id,
        expected_amount: expectedAmount,
        variance_reason: needsJustification ? (reason as CashVarianceReason) : null,
        variance_note: needsJustification ? note.trim() : null,
      });
      onChanged();
    } catch (err) {
      setCloseError(cashErrorMessage(err));
      onChanged(); // situation possiblement changée (409) : on recharge pour réafficher le vrai état
    } finally {
      setIsClosing(false);
    }
  }

  return (
    <>
      <section aria-labelledby="cash-count-title" className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <h2 id="cash-count-title" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          Comptage par coupure
        </h2>
        {denominations.length === 0 ? (
          <p className="text-sm text-red-700">Aucun référentiel de coupures pour la devise {currency}.</p>
        ) : (
          <form
            aria-label="Comptage physique"
            onSubmit={(e) => {
              e.preventDefault();
              void submitCount();
            }}
            className="flex flex-col gap-3"
          >
            {/* Nombre de colonnes selon la place réelle du bloc (souvent la colonne étroite de droite),
                pas selon la largeur de l'écran : chaque case garde le montant sur une ligne, avec la
                quantité dessous. Vérifié le 2026-11-16 : avant, à 4 colonnes, montants coupés et
                champs débordant sur la case voisine. */}
            <div className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2">
              {denominations.map((denomination) => (
                <label
                  key={denomination}
                  className="flex min-w-0 flex-col gap-1 rounded-lg border border-slate-200 px-2 py-2 text-sm"
                >
                  <span className="whitespace-nowrap font-medium text-slate-800">
                    {formatApiAmount(denomination, currency)}
                  </span>
                  <input
                    aria-label={`Quantité de ${formatApiAmount(denomination, currency)}`}
                    value={quantities[denomination] ?? ""}
                    onChange={(e) => setQuantities((prev) => ({ ...prev, [denomination]: e.target.value }))}
                    inputMode="numeric"
                    placeholder="0"
                    className="w-full min-w-0 min-h-11 rounded-lg border border-slate-300 px-2 text-right tabular-nums sm:min-h-9 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-600">
                Aperçu :{" "}
                <span data-testid="cash-count-preview" className="font-semibold text-slate-900">
                  {previewCents === null ? "quantité invalide" : formatMoney(previewCents, currency)}
                </span>
                <span className="ml-1 text-xs text-slate-600">(total officiel calculé par le serveur)</span>
              </p>
              <button
                type="submit"
                disabled={invalid || isCounting}
                className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-40"
              >
                {isCounting ? "Enregistrement..." : latestCount ? "Enregistrer un nouveau comptage" : "Enregistrer le comptage"}
              </button>
            </div>
            {countError && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {countError}
              </p>
            )}
          </form>
        )}
        {latestCount && (
          <p className="text-xs text-slate-600">
            Dernier comptage le {formatDateTime(latestCount.counted_at)} :{" "}
            <span data-testid="cash-counted-amount" className="font-semibold text-slate-900">
              {formatApiAmount(latestCount.total_amount, currency)}
            </span>
          </p>
        )}
      </section>

      <section aria-labelledby="cash-close-title" className="flex flex-col gap-3 rounded-xl border border-slate-300 bg-white p-4">
        <h2 id="cash-close-title" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          Écart et clôture
        </h2>
        {latestCount === null || varianceCents === null ? (
          <p className="text-sm text-slate-600">Enregistrez un comptage physique pour calculer l&apos;écart et clôturer.</p>
        ) : (
          <>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-slate-600">Théorique</dt>
                <dd className="font-semibold">{formatApiAmount(expectedAmount, currency)}</dd>
              </div>
              <div>
                <dt className="text-slate-600">Physique</dt>
                <dd className="font-semibold">{formatApiAmount(latestCount.total_amount, currency)}</dd>
              </div>
              <div>
                <dt className="text-slate-600">Écart</dt>
                <dd
                  data-testid="cash-variance"
                  className={`text-lg font-bold ${varianceCents === 0 ? "text-emerald-800" : "text-red-700"}`}
                >
                  {varianceCents > 0 ? "+" : ""}
                  {formatMoney(varianceCents, currency)}
                </dd>
              </div>
            </dl>
            {needsJustification && (
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Motif de l&apos;écart
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value as CashVarianceReason | "")}
                    className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
                  >
                    <option value="">Choisir…</option>
                    {varianceReasons.map((code) => (
                      <option key={code} value={code}>
                        {CASH_VARIANCE_REASON_LABELS[code] ?? code}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Justification de l&apos;écart
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={2000}
                    rows={2}
                    className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
                  />
                </label>
              </div>
            )}
            {closeError && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {closeError}
              </p>
            )}
            <button
              type="button"
              onClick={() => void submitClose()}
              disabled={!canClose}
              className="rounded-lg bg-red-800 px-4 py-3 text-sm font-semibold text-white hover:bg-red-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isClosing ? "Clôture..." : "Clôturer la caisse"}
            </button>
            <p className="text-xs text-slate-600">
              Après clôture, plus aucun encaissement, mouvement ni comptage ne peut être ajouté à cette session.
            </p>
          </>
        )}
      </section>
    </>
  );
}
