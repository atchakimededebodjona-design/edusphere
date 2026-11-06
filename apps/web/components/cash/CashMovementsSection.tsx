"use client";

import { useRef, useState } from "react";
import { cashRegister, type CashMovement, type CashMovementDirection, type CashMovementType } from "@/lib/cash/client";
import { cashErrorMessage } from "@/lib/cash/errors";
import { CASH_MOVEMENT_TYPE_LABELS } from "@/lib/cash/labels";
import { centsToApi, formatApiAmount, newIdempotencyKey, toCents } from "@/lib/fees/allocation";

const TYPES: CashMovementType[] = ["CASH_IN", "CASH_OUT", "BANK_DEPOSIT", "OTHER"];

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** Mouvements d'espèces hors paiements d'élèves (apport, dépense, versement banque…). */
export function CashMovementsSection({
  sessionId,
  movements,
  currency,
  canManage,
  onChanged,
}: {
  sessionId: string;
  movements: CashMovement[];
  currency: string;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [type, setType] = useState<CashMovementType>("CASH_IN");
  const [direction, setDirection] = useState<CashMovementDirection | "">("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Une clé par mouvement saisi, réutilisée si la même saisie est renvoyée (retry / double clic).
  const key = useRef<string | null>(null);

  const cents = toCents(amount);
  const canSubmit =
    cents !== null && cents > 0 && reason.trim().length > 0 && (type !== "OTHER" || direction !== "") && !isSubmitting;

  function edited() {
    key.current = null;
    setError(null);
  }

  async function submit() {
    if (!canSubmit || cents === null) return;
    key.current ??= newIdempotencyKey();
    setIsSubmitting(true);
    setError(null);
    try {
      await cashRegister.addMovement(sessionId, {
        type,
        direction: type === "OTHER" ? (direction as CashMovementDirection) : null,
        amount: centsToApi(cents),
        reason: reason.trim(),
        reference: reference.trim() || null,
        idempotency_key: key.current,
      });
      key.current = null;
      setAmount("");
      setReason("");
      setReference("");
      onChanged();
    } catch (err) {
      setError(cashErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section aria-labelledby="cash-movements-title" className="flex flex-col gap-3 rounded border border-slate-200 bg-white p-4">
      <h2 id="cash-movements-title" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
        Mouvements de caisse
      </h2>
      {canManage && (
        <form
          aria-label="Nouveau mouvement"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
        >
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Type de mouvement
            <select
              value={type}
              onChange={(e) => {
                edited();
                setType(e.target.value as CashMovementType);
              }}
              className="rounded border border-slate-300 px-2 py-2 text-sm"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {CASH_MOVEMENT_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
          {type === "OTHER" && (
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Sens
              <select
                value={direction}
                onChange={(e) => {
                  edited();
                  setDirection(e.target.value as CashMovementDirection | "");
                }}
                className="rounded border border-slate-300 px-2 py-2 text-sm"
              >
                <option value="">Choisir…</option>
                <option value="IN">Entrée</option>
                <option value="OUT">Sortie</option>
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Montant du mouvement
            <input
              value={amount}
              onChange={(e) => {
                edited();
                setAmount(e.target.value);
              }}
              inputMode="decimal"
              autoComplete="off"
              className="rounded border border-slate-300 px-2 py-2 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600 sm:col-span-2 lg:col-span-1">
            Motif du mouvement
            <input
              value={reason}
              onChange={(e) => {
                edited();
                setReason(e.target.value);
              }}
              maxLength={500}
              className="rounded border border-slate-300 px-2 py-2 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Référence (facultatif)
            <input
              value={reference}
              onChange={(e) => {
                edited();
                setReference(e.target.value);
              }}
              maxLength={255}
              className="rounded border border-slate-300 px-2 py-2 text-sm"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!canSubmit}
              className="w-full rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-40"
            >
              {isSubmitting ? "Enregistrement..." : "Enregistrer le mouvement"}
            </button>
          </div>
          {error && (
            <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 sm:col-span-2 lg:col-span-3">
              {error}
            </p>
          )}
        </form>
      )}
      {movements.length === 0 ? (
        <p className="text-sm text-slate-500">Aucun mouvement.</p>
      ) : (
        <ul aria-label="Mouvements enregistrés" className="divide-y divide-slate-100 text-sm">
          {movements.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">
                  {CASH_MOVEMENT_TYPE_LABELS[m.type]}
                  {m.type === "OTHER" && ` (${m.direction === "IN" ? "entrée" : "sortie"})`}
                  <span className="ml-2 text-xs font-normal text-slate-500">{formatTime(m.created_at)}</span>
                </p>
                <p className="truncate text-xs text-slate-600">
                  {m.reason}
                  {m.reference ? ` · Réf. ${m.reference}` : ""}
                </p>
              </div>
              <span className={`font-semibold ${m.direction === "IN" ? "text-emerald-800" : "text-red-700"}`}>
                {m.direction === "IN" ? "+" : "−"}
                {formatApiAmount(m.amount, currency)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
