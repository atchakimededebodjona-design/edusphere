// Phase 29, lot A — abonnements des écoles (api: modules/subscriptions). Types alignés sur
// apps/api/app/modules/subscriptions/schemas.py ; montants = chaînes décimales de l'API (jamais de
// flottant). Le client n'envoie JAMAIS de montant côté école : uniquement la durée choisie.
// Ce module ne fait qu'appeler l'API : toutes les permissions sont vérifiées côté serveur.
import { apiFetch } from "@/lib/api/client";
import type { Page } from "@/lib/platform/client";

export type PeriodMonths = 3 | 6 | 12;
export const PERIOD_MONTHS: PeriodMonths[] = [3, 6, 12];

export type SubscriptionState = "NONE" | "SCHEDULED" | "TRIAL" | "ACTIVE" | "EXPIRING_SOON" | "EXPIRED";
export type InvoiceStatus = "QUOTE_REQUIRED" | "ISSUED" | "PAID" | "EXPIRED" | "CANCELLED";
export type PeriodKind = "FREE_TRIAL" | "PAID";
export type ManualPaymentMethod = "FLOOZ" | "TMONEY" | "BANK_TRANSFER" | "CASH" | "OTHER";

export type SubscriptionPeriod = {
  id: string;
  kind: PeriodKind;
  starts_on: string;
  ends_on: string;
  invoice_id: string | null;
};

export type SubscriptionOffer = {
  period_months: PeriodMonths;
  base_amount: string | null;
  supplement_amount: string | null;
  total_amount: string | null;
};

export type InvoiceSummary = {
  id: string;
  number: string | null;
  status: InvoiceStatus;
  period_months: PeriodMonths;
  student_count: number;
  tier: number | null;
  total_amount: string | null;
  currency: string;
  issued_at: string | null;
  expires_at: string | null;
  paid_at: string | null;
  created_at: string;
};

export type SubscriptionPayment = {
  id: string;
  provider: "PAYGATE" | "MANUAL";
  method: ManualPaymentMethod;
  status: string;
  amount: string;
  currency: string;
  reference: string | null;
  confirmed_at: string | null;
  created_at: string;
};

export type Invoice = InvoiceSummary & {
  school_id: string;
  organization_id: string;
  base_amount: string | null;
  supplement_amount: string | null;
  grid_id: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  payments: SubscriptionPayment[];
  period: SubscriptionPeriod | null;
};

export type PlatformInvoice = Invoice & { school_name: string };

export type SchoolSubscription = {
  school_id: string;
  school_name: string;
  today: string;
  state: SubscriptionState;
  current_period: SubscriptionPeriod | null;
  covered_until: string | null;
  next_period_starts_on: string | null;
  active_student_count: number;
  tier: number | null;
  quote_required: boolean;
  grid_available: boolean;
  currency: string;
  offers: SubscriptionOffer[];
  open_invoice: InvoiceSummary | null;
  periods: SubscriptionPeriod[];
};

export type GridPeriodPrices = {
  period_months: PeriodMonths;
  base_amount: string;
  supplement_tier_1: string;
  supplement_tier_2: string;
  supplement_tier_3: string;
};

export type PriceGrid = {
  id: string;
  label: string;
  currency: string;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  created_at: string;
  activated_at: string | null;
  archived_at: string | null;
  periods: GridPeriodPrices[];
};

export type GridInput = { label: string; periods: GridPeriodPrices[] };

export type PlatformSchoolSubscription = {
  school_id: string;
  school_name: string;
  organization_id: string;
  state: SubscriptionState;
  current_period_kind: PeriodKind | null;
  covered_until: string | null;
  next_period_starts_on: string | null;
  has_free_trial: boolean;
  open_invoice_status: InvoiceStatus | null;
  active_student_count: number;
};

/** Même règle que lib/fees/allocation.ts::newIdempotencyKey (8 à 128 caractères côté API) :
 * `randomUUID` n'existe que dans un contexte sécurisé, d'où le repli sur `getRandomValues`. */
function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `${prefix}-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

async function json<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

async function blobUrl(response: Response): Promise<string> {
  return URL.createObjectURL(await response.blob());
}

function postJson(path: string, body: unknown, method = "POST"): Promise<Response> {
  return apiFetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

// --- École ---------------------------------------------------------------------------------------
export const schoolSubscription = {
  get: async (schoolId: string) =>
    json<SchoolSubscription>(await apiFetch(`/api/v1/school-subscription?school_id=${encodeURIComponent(schoolId)}`)),
  invoices: async (schoolId: string) =>
    json<InvoiceSummary[]>(
      await apiFetch(`/api/v1/school-subscription/invoices?school_id=${encodeURIComponent(schoolId)}`),
    ),
  invoice: async (invoiceId: string) =>
    json<Invoice>(await apiFetch(`/api/v1/school-subscription/invoices/${encodeURIComponent(invoiceId)}`)),
  /** La clé d'idempotence est créée par l'appelant UNE fois par intention d'achat : un double clic
   * ou un nouvel essai réseau renvoie la même facture au lieu d'en créer une seconde. */
  issueInvoice: async (schoolId: string, periodMonths: PeriodMonths, idempotencyKey: string) =>
    json<Invoice>(
      await postJson("/api/v1/school-subscription/invoices", {
        school_id: schoolId,
        period_months: periodMonths,
        idempotency_key: idempotencyKey,
      }),
    ),
  newIdempotencyKey: () => newIdempotencyKey("subinv"),
  /** Lot C — reçu PDF d'une facture payée (409 sinon), ouvert via une URL de blob locale. */
  receiptBlobUrl: async (invoiceId: string) =>
    blobUrl(await apiFetch(`/api/v1/school-subscription/invoices/${encodeURIComponent(invoiceId)}/receipt.pdf`)),
};

// --- Plateforme ----------------------------------------------------------------------------------
export const platformSubscriptions = {
  grids: async () => json<PriceGrid[]>(await apiFetch("/api/v1/platform/subscription-grids")),
  createGrid: async (input: GridInput) => json<PriceGrid>(await postJson("/api/v1/platform/subscription-grids", input)),
  updateGrid: async (gridId: string, input: GridInput) =>
    json<PriceGrid>(await postJson(`/api/v1/platform/subscription-grids/${encodeURIComponent(gridId)}`, input, "PUT")),
  activateGrid: async (gridId: string) =>
    json<PriceGrid>(await postJson(`/api/v1/platform/subscription-grids/${encodeURIComponent(gridId)}/activate`, {})),

  schools: async (page: number, pageSize: number, state: SubscriptionState | "") => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (state) params.set("state", state);
    return json<Page<PlatformSchoolSubscription>>(await apiFetch(`/api/v1/platform/subscriptions?${params}`));
  },

  invoices: async (page: number, pageSize: number, status: InvoiceStatus | "") => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set("status", status);
    return json<Page<PlatformInvoice>>(await apiFetch(`/api/v1/platform/subscription-invoices?${params}`));
  },
  setQuote: async (invoiceId: string, totalAmount: string) =>
    json<PlatformInvoice>(
      await postJson(`/api/v1/platform/subscription-invoices/${encodeURIComponent(invoiceId)}/quote`, {
        total_amount: totalAmount,
      }),
    ),
  cancel: async (invoiceId: string, reason: string) =>
    json<PlatformInvoice>(
      await postJson(`/api/v1/platform/subscription-invoices/${encodeURIComponent(invoiceId)}/cancel`, { reason }),
    ),
  recordManualPayment: async (
    invoiceId: string,
    input: { method: ManualPaymentMethod; amount: string; reference: string; idempotency_key: string },
  ) =>
    json<PlatformInvoice>(
      await postJson(`/api/v1/platform/subscription-invoices/${encodeURIComponent(invoiceId)}/manual-payments`, input),
    ),
  newIdempotencyKey: () => newIdempotencyKey("subpay"),
  receiptBlobUrl: async (invoiceId: string) =>
    blobUrl(await apiFetch(`/api/v1/platform/subscription-invoices/${encodeURIComponent(invoiceId)}/receipt.pdf`)),
};

// --- Libellés ------------------------------------------------------------------------------------
export const STATE_LABELS: Record<SubscriptionState, string> = {
  NONE: "Aucun abonnement",
  SCHEDULED: "Période programmée",
  TRIAL: "Trimestre gratuit",
  ACTIVE: "Abonnement actif",
  EXPIRING_SOON: "Expire bientôt",
  EXPIRED: "Expiré",
};

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  QUOTE_REQUIRED: "Devis en attente",
  ISSUED: "À payer",
  PAID: "Payée",
  EXPIRED: "Expirée",
  CANCELLED: "Annulée",
};

export const PERIOD_KIND_LABELS: Record<PeriodKind, string> = {
  FREE_TRIAL: "Trimestre gratuit",
  PAID: "Abonnement payé",
};

export const MANUAL_METHOD_LABELS: Record<ManualPaymentMethod, string> = {
  BANK_TRANSFER: "Virement bancaire",
  FLOOZ: "Flooz",
  TMONEY: "T-Money",
  CASH: "Espèces",
  OTHER: "Autre",
};

export function periodLabel(months: number): string {
  return months === 12 ? "12 mois (annuel)" : months === 6 ? "6 mois (semestriel)" : "3 mois (trimestriel)";
}
