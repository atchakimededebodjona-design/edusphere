// Commissions des partenaires (api: modules/commissions, migration 0031). Montants = chaînes
// décimales de l'API (jamais de flottant). Ce module ne fait qu'appeler l'API : toutes les
// permissions sont vérifiées côté serveur (`platform.commissions.*`, `partner.commissions.read`).
import { apiFetch } from "@/lib/api/client";

export type CommissionStatus = "DUE" | "PAID" | "CANCELLED";
export type SettlementMethod = "MOBILE_MONEY" | "BANK_TRANSFER" | "CASH" | "OTHER";

export type Commission = {
  id: string;
  partner_id: string;
  partner_name: string;
  school_id: string;
  school_name: string;
  invoice_id: string;
  invoice_number: string | null;
  period_months: number;
  base_amount_excl_vat: string;
  rate: string;
  amount: string;
  currency: string;
  status: CommissionStatus;
  created_at: string;
  paid_at: string | null;
  settlement_method: SettlementMethod | null;
  settlement_reference: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
};

export type CommissionTotals = {
  due_amount: string;
  due_count: number;
  paid_amount: string;
  paid_count: number;
};

export type CommissionsPage = {
  items: Commission[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  totals: CommissionTotals;
};

export type PartnerCommissions = { commission_rate: string; totals: CommissionTotals; items: Commission[] };

function postJson(path: string, body: unknown, method = "POST"): Promise<Response> {
  return apiFetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const platformCommissions = {
  list: async (page: number, pageSize: number, status: CommissionStatus | "", partnerId: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set("status", status);
    if (partnerId) params.set("partner_id", partnerId);
    return (await (await apiFetch(`/api/v1/platform/partner-commissions?${params}`)).json()) as CommissionsPage;
  },
  markPaid: async (commissionIds: string[], method: SettlementMethod, reference: string) =>
    (await (
      await postJson("/api/v1/platform/partner-commissions/mark-paid", {
        commission_ids: commissionIds,
        method,
        reference,
      })
    ).json()) as string[],
  cancel: async (commissionId: string, reason: string) =>
    postJson(`/api/v1/platform/partner-commissions/${encodeURIComponent(commissionId)}/cancel`, { reason }),
  setRate: async (partnerId: string, rate: string) =>
    postJson(`/api/v1/platform/partners/${encodeURIComponent(partnerId)}/commission-rate`, { rate }, "PUT"),
};

export const partnerCommissions = {
  own: async () => (await (await apiFetch("/api/v1/partner/commissions")).json()) as PartnerCommissions,
};

export const COMMISSION_STATUS_LABELS: Record<CommissionStatus, string> = {
  DUE: "À verser",
  PAID: "Versée",
  CANCELLED: "Annulée",
};

export const SETTLEMENT_METHOD_LABELS: Record<SettlementMethod, string> = {
  MOBILE_MONEY: "Mobile Money",
  BANK_TRANSFER: "Virement bancaire",
  CASH: "Espèces",
  OTHER: "Autre",
};
