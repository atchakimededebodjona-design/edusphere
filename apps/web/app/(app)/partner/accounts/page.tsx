"use client";

import { DataTable, TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Badge, EmptyState, PageHeader } from "@/components/ui/Surface";
import { ASSIGNABLE_ROLES } from "@/lib/users/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { listPartnerAccounts } from "@/lib/partners/client";

const ROLE_LABELS: Record<string, string> = Object.fromEntries(ASSIGNABLE_ROLES.map((r) => [r.value, r.label]));

// PR #17 — comptes des écoles inscrites par CE partenaire (métadonnées uniquement, filtrées par
// l'API — jamais de donnée académique ou financière).
export default function PartnerAccountsPage() {
  const { data, error, isLoading, retry } = useAsyncData(listPartnerAccounts, []);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Comptes" description="Comptes utilisateurs des écoles que vous avez inscrites." />
      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <TableSkeleton />}
      {data && (
        <DataTable
          caption="Comptes"
          rows={data}
          rowKey={(account) => account.id}
          empty={<EmptyState icon="users" title="Aucun compte." />}
          columns={[
            { key: "name", header: "Nom", mobile: "title", cell: (account) => account.full_name },
            { key: "email", header: "Email", mobile: "full", cell: (account) => <span className="break-all">{account.email}</span> },
            { key: "roles", header: "Rôles", cell: (account) => account.role_codes.map((code) => ROLE_LABELS[code] ?? code).join(", ") },
            {
              key: "status",
              header: "Statut",
              cell: (account) => <Badge tone={account.is_active ? "success" : "neutral"}>{account.is_active ? "Actif" : "Inactif"}</Badge>,
            },
            { key: "created", header: "Créé le", cell: (account) => new Date(account.created_at).toLocaleDateString("fr-FR") },
          ]}
        />
      )}
    </div>
  );
}
