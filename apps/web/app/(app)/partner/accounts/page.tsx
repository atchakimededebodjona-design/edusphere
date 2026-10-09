"use client";

import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { listPartnerAccounts } from "@/lib/partners/client";

// PR #17 — comptes des écoles inscrites par CE partenaire (métadonnées uniquement, filtrées par
// l'API — jamais de donnée académique ou financière).
export default function PartnerAccountsPage() {
  const { data, error, isLoading, retry } = useAsyncData(listPartnerAccounts, []);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Comptes</h1>
        <p className="text-sm text-slate-600">Comptes utilisateurs des écoles que vous avez inscrites.</p>
      </div>
      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}
      {data &&
        (data.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun compte.</p>
        ) : (
          <div className="overflow-x-auto rounded border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Email</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Rôles</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Créé le</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((account) => (
                  <tr key={account.id}>
                    <td className="px-3 py-2 text-slate-700">{account.full_name}</td>
                    <td className="px-3 py-2 text-slate-700">{account.email}</td>
                    <td className="px-3 py-2 text-slate-700">{account.role_codes.join(", ")}</td>
                    <td className="px-3 py-2 text-slate-700">{account.is_active ? "Actif" : "Inactif"}</td>
                    <td className="px-3 py-2 text-slate-700">{new Date(account.created_at).toLocaleDateString("fr-FR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  );
}
