import type { PaymentMethod, PaymentStatus, StudentFeeStatus } from "@/lib/fees/client";

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: "Espèces",
  BANK_TRANSFER: "Virement",
  CHEQUE: "Chèque",
  AGENT_DEPOSIT: "Dépôt agent",
  OTHER: "Autre",
};

export const PAYMENT_STATUS_LABELS: Record<PaymentStatus, string> = {
  COMPLETED: "Enregistré",
  CANCELLED: "Annulé",
};

export const STUDENT_FEE_STATUS_LABELS: Record<StudentFeeStatus, string> = {
  PENDING: "Non payé",
  PARTIALLY_PAID: "Partiellement payé",
  PAID: "Soldé",
  CANCELLED: "Annulé",
};
