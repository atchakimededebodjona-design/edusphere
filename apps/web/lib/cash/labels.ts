import type { CashMovementType, CashSessionStatus, CashVarianceReason } from "@/lib/cash/client";

export const CASH_MOVEMENT_TYPE_LABELS: Record<CashMovementType, string> = {
  CASH_IN: "Entrée d'espèces",
  CASH_OUT: "Sortie d'espèces",
  BANK_DEPOSIT: "Versement en banque",
  OTHER: "Autre mouvement",
};

export const CASH_SESSION_STATUS_LABELS: Record<CashSessionStatus, string> = {
  OPEN: "Ouverte",
  CLOSED: "Clôturée",
};

export const CASH_VARIANCE_REASON_LABELS: Record<CashVarianceReason, string> = {
  COUNTING_ERROR: "Erreur de comptage",
  CHANGE_ERROR: "Erreur de rendu de monnaie",
  UNRECORDED_PAYMENT: "Encaissement non enregistré",
  UNRECORDED_MOVEMENT: "Mouvement non enregistré",
  LOSS_OR_THEFT: "Perte ou vol",
  OTHER: "Autre",
};
