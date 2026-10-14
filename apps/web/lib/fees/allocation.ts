// Caisse scolaire, lot 2 — calculs de montants et de répartition côté interface.
//
// Tout est fait en CENTIMES ENTIERS (jamais en flottants) : les montants de l'API sont des chaînes
// décimales à 2 chiffres ("150000.00"). Ces règles ne font que rendre lisible, avant envoi, ce que
// le backend impose déjà (fees/service.py::record_payment) : somme des allocations == montant reçu,
// aucune allocation au-delà du solde restant. Le backend reste l'autorité.

import type { StudentFeeWithBalance } from "@/lib/fees/client";

const AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

/** "50000", "50 000", "50000,5", "150000.00" -> centimes entiers ; null si invalide ou vide. */
export function toCents(value: string): number | null {
  const normalized = value.replace(/[\s  ]/g, "").replace(",", ".");
  if (!AMOUNT_PATTERN.test(normalized)) return null;
  const [units, decimals = ""] = normalized.split(".");
  const cents = Number(units) * 100 + Number(decimals.padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

/** Centimes -> chaîne décimale attendue par l'API ("40000.00"). */
export function centsToApi(cents: number): string {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

/** Centimes -> saisie éditable ("40000", ou "40000.50" si décimales). */
export function centsToInput(cents: number): string {
  return cents % 100 === 0 ? String(cents / 100) : centsToApi(cents);
}

const CURRENCY_LABELS: Record<string, string> = { XOF: "FCFA", XAF: "FCFA" };

export function currencyLabel(currency: string): string {
  return CURRENCY_LABELS[currency] ?? currency;
}

/** 15000000 centimes, "XOF" -> "150 000 FCFA" (décimales affichées seulement si non nulles). */
export function formatMoney(cents: number, currency: string): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const units = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const decimals = abs % 100 === 0 ? "" : `,${String(abs % 100).padStart(2, "0")}`;
  const label = currencyLabel(currency);
  return `${sign}${units}${decimals}${label ? ` ${label}` : ""}`;
}

/** Montant API ("150000.00") -> affichage ; tel quel si illisible. */
export function formatApiAmount(amount: string, currency: string): string {
  const cents = toCents(amount);
  return cents === null ? amount : formatMoney(cents, currency);
}

export type AllocatableFee = { id: string; balanceCents: number; dueDate: string | null; createdAt: string };

export function toAllocatableFees(fees: StudentFeeWithBalance[]): AllocatableFee[] {
  return fees
    .filter((fee) => fee.status !== "CANCELLED")
    .map((fee) => ({
      id: fee.id,
      balanceCents: Math.max(toCents(fee.balance) ?? 0, 0),
      dueDate: fee.due_date,
      createdAt: fee.created_at,
    }));
}

/** Ordre de répartition : échéance la plus proche d'abord (sans échéance en dernier), puis le
 * frais le plus ancien. */
export function allocationOrder(fees: AllocatableFee[]): AllocatableFee[] {
  return [...fees].sort((a, b) => {
    if (a.dueDate !== b.dueDate) {
      if (a.dueDate === null) return 1;
      if (b.dueDate === null) return -1;
      return a.dueDate < b.dueDate ? -1 : 1;
    }
    return a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0;
  });
}

/** Répartit `amountCents` frais par frais dans `allocationOrder`, sans jamais dépasser un solde.
 * Le reliquat éventuel (montant > total des soldes) reste NON affecté : jamais de trop-perçu. */
export function autoAllocate(fees: AllocatableFee[], amountCents: number): Record<string, number> {
  const result: Record<string, number> = {};
  let remaining = Math.max(amountCents, 0);
  for (const fee of allocationOrder(fees)) {
    const share = Math.min(fee.balanceCents, remaining);
    result[fee.id] = share;
    remaining -= share;
  }
  return result;
}

export function totalBalanceCents(fees: AllocatableFee[]): number {
  return fees.reduce((sum, fee) => sum + fee.balanceCents, 0);
}

export type AllocationCheck = {
  amountCents: number | null;
  allocatedCents: number;
  unallocatedCents: number;
  invalidFeeIds: string[];
  exceedingFeeIds: string[];
  canSubmit: boolean;
  reason: string | null;
};

/** Vérifie la saisie : `amountInput` (montant reçu) et `allocationInputs` (par frais). */
export function checkAllocation(
  fees: AllocatableFee[],
  amountInput: string,
  allocationInputs: Record<string, string>,
): AllocationCheck {
  const amountCents = amountInput.trim() === "" ? null : toCents(amountInput);
  let allocatedCents = 0;
  const invalidFeeIds: string[] = [];
  const exceedingFeeIds: string[] = [];
  for (const fee of fees) {
    const raw = (allocationInputs[fee.id] ?? "").trim();
    if (raw === "") continue;
    const cents = toCents(raw);
    if (cents === null) {
      invalidFeeIds.push(fee.id);
      continue;
    }
    if (cents > fee.balanceCents) exceedingFeeIds.push(fee.id);
    allocatedCents += cents;
  }
  const unallocatedCents = (amountCents ?? 0) - allocatedCents;

  let reason: string | null = null;
  if (amountCents === null || amountCents <= 0) reason = "Saisissez un montant reçu supérieur à 0.";
  else if (invalidFeeIds.length > 0) reason = "Un montant affecté est invalide.";
  else if (exceedingFeeIds.length > 0) reason = "Un montant affecté dépasse le solde restant du frais.";
  else if (allocatedCents !== amountCents) reason = "Le total affecté doit être égal au montant reçu.";

  return {
    amountCents,
    allocatedCents,
    unallocatedCents,
    invalidFeeIds,
    exceedingFeeIds,
    canSubmit: reason === null,
    reason,
  };
}

/** Clé d'idempotence unique par opération d'encaissement (8 à 128 caractères côté API). */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `cash-${crypto.randomUUID()}`;
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `cash-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

/** Date locale du poste de caisse au format API (YYYY-MM-DD). */
export function localIsoDate(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
