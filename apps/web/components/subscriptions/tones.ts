import type { Tone } from "@/components/ui/Surface";
import type { InvoiceStatus, PaymentStatus, SubscriptionState } from "@/lib/subscriptions/client";

// Refonte, phase 4 A (2026-11-24) — couleur des pastilles d'abonnement, de facture et de paiement en
// ligne. Les libellés restent ceux de `lib/subscriptions/client.ts`.
export const STATE_TONES: Record<SubscriptionState, Tone> = {
  NONE: "neutral",
  SCHEDULED: "info",
  TRIAL: "info",
  ACTIVE: "success",
  EXPIRING_SOON: "warning",
  EXPIRED: "danger",
};

export const INVOICE_STATUS_TONES: Record<InvoiceStatus, Tone> = {
  QUOTE_REQUIRED: "neutral",
  ISSUED: "warning",
  PAID: "success",
  EXPIRED: "danger",
  CANCELLED: "neutral",
};

export const PAYMENT_STATUS_TONES: Record<PaymentStatus, Tone> = {
  INITIATED: "info",
  PENDING: "info",
  SUCCEEDED: "success",
  FAILED: "danger",
  EXPIRED: "neutral",
  ANOMALY: "danger",
};
