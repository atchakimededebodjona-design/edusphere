"use client";

import { listPlatformAccounts, type PlatformAccount } from "@/lib/platform/client";
import { formatDate, PlatformListPage } from "../PlatformListPage";

export default function PlatformAccountsPage() {
  return (
    <PlatformListPage<PlatformAccount>
      title="Comptes"
      description="Comptes utilisateurs de la plateforme (métadonnées uniquement)."
      fetchPage={listPlatformAccounts}
      rowKey={(account) => account.id}
      columns={[
        { header: "Nom", render: (account) => account.full_name },
        { header: "Email", render: (account) => account.email },
        { header: "Rôles", render: (account) => account.role_codes.join(", ") || "—" },
        { header: "Statut", render: (account) => (account.is_active ? "Actif" : "Inactif") },
        { header: "Créé le", render: (account) => formatDate(account.created_at) },
      ]}
    />
  );
}
