"use client";

import { useState } from "react";
import { formatDateFR } from "@/lib/format/date";
import {
  INVOICE_STATUS_LABELS,
  PERIOD_KIND_LABELS,
  STATE_LABELS,
  platformSubscriptions,
  type PlatformSchoolSubscription,
  type SubscriptionState,
} from "@/lib/subscriptions/client";
import { PlatformListPage } from "../PlatformListPage";

const STATES = Object.keys(STATE_LABELS) as SubscriptionState[];

// Phase 29, lot A — état de l'abonnement de chaque école (calculé par l'API, jamais stocké). Aucun
// blocage n'est appliqué aux écoles expirées (décision « rappels seulement »).
export default function PlatformSubscriptionsPage() {
  const [state, setState] = useState<SubscriptionState | "">("");
  const [reloadKey, setReloadKey] = useState(0);

  return (
    <PlatformListPage<PlatformSchoolSubscription>
      title="Abonnements des écoles"
      description="Trimestre gratuit, abonnement en cours, échéance et facture ouverte de chaque école."
      fetchPage={(page, pageSize) => platformSubscriptions.schools(page, pageSize, state)}
      rowKey={(row) => row.school_id}
      reloadKey={reloadKey}
      columns={[
        { header: "École", render: (row) => row.school_name },
        { header: "État", render: (row) => STATE_LABELS[row.state] },
        { header: "Période en cours", render: (row) => (row.current_period_kind ? PERIOD_KIND_LABELS[row.current_period_kind] : "—") },
        { header: "Couvert jusqu'au", render: (row) => (row.covered_until ? formatDateFR(row.covered_until) : "—") },
        { header: "Trimestre gratuit", render: (row) => (row.has_free_trial ? "Attribué" : "Pas encore") },
        { header: "Facture ouverte", render: (row) => (row.open_invoice_status ? INVOICE_STATUS_LABELS[row.open_invoice_status] : "—") },
        { header: "Élèves actifs", render: (row) => String(row.active_student_count) },
      ]}
    >
      <label className="flex items-center gap-2 text-sm text-slate-700">
        État
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value as SubscriptionState | "");
            setReloadKey((k) => k + 1);
          }}
          className="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">Tous</option>
          {STATES.map((code) => (
            <option key={code} value={code}>
              {STATE_LABELS[code]}
            </option>
          ))}
        </select>
      </label>
    </PlatformListPage>
  );
}
