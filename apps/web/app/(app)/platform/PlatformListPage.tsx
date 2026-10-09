"use client";

import { useState, type ReactNode } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { useAsyncData } from "@/lib/api/useAsyncData";
import type { Page } from "@/lib/platform/client";

const PAGE_SIZE = 20;

export type Column<T> = {
  header: string;
  render: (row: T) => ReactNode;
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

/** Liste plateforme paginée en lecture seule (PR #17) — métadonnées uniquement. Les données
 * affichées sont déjà filtrées par l'API (permission `platform.*` vérifiée côté serveur) : ce
 * composant n'applique aucun contrôle d'accès lui-même. `reloadKey` force un rechargement (ex.
 * après création d'un partenaire). */
export function PlatformListPage<T>({
  title,
  description,
  fetchPage,
  columns,
  rowKey,
  reloadKey = 0,
  children,
}: {
  title: string;
  description: string;
  fetchPage: (page: number, pageSize: number) => Promise<Page<T>>;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  reloadKey?: number;
  children?: ReactNode;
}) {
  const [page, setPage] = useState(1);
  const { data, error, isLoading, isRefreshing, retry } = useAsyncData(
    () => fetchPage(page, PAGE_SIZE),
    [page, reloadKey],
  );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        <p className="text-sm text-slate-600">{description}</p>
      </div>

      {children}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}

      {data && (
        <>
          <p className="text-sm text-slate-500">
            {data.total} résultat{data.total > 1 ? "s" : ""}
            {isRefreshing && " — actualisation..."}
          </p>
          {data.items.length === 0 ? (
            <p className="text-sm text-slate-500">Aucun élément.</p>
          ) : (
            <div className="overflow-x-auto rounded border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    {columns.map((column) => (
                      <th key={column.header} className="px-3 py-2 text-left font-medium text-slate-600">
                        {column.header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((row) => (
                    <tr key={rowKey(row)}>
                      {columns.map((column) => (
                        <td key={column.header} className="px-3 py-2 text-slate-700">
                          {column.render(row)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.total_pages > 1 && (
            <div className="flex items-center gap-3 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
              >
                Précédent
              </button>
              <span className="text-slate-600">
                Page {data.page} / {data.total_pages}
              </span>
              <button
                type="button"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
              >
                Suivant
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
