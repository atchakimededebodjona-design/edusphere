"use client";

import { useState, type ReactNode } from "react";
import { DataTable, Pager, TableSkeleton, type Column as TableColumn } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { EmptyState, PageHeader } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import type { Page } from "@/lib/platform/client";

const PAGE_SIZE = 20;

export type Column<T> = {
  header: string;
  render: (row: T) => ReactNode;
  /** Place sur téléphone (voir `DataTable`) ; par défaut, la première colonne sert de titre de carte. */
  mobile?: TableColumn<T>["mobile"];
  align?: "left" | "right";
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

/** Liste plateforme paginée en lecture seule (PR #17) — métadonnées uniquement. Les données
 * affichées sont déjà filtrées par l'API (permission `platform.*` vérifiée côté serveur) : ce
 * composant n'applique aucun contrôle d'accès lui-même. `reloadKey` force un rechargement (ex.
 * après création d'un partenaire).
 *
 * Refonte, phase 4 A (2026-11-24) : tableau commun (cartes sur téléphone), pagination commune, état
 * vide et squelette de chargement. Mêmes colonnes, mêmes en-têtes, même texte dans les cellules. */
export function PlatformListPage<T>({
  title,
  description,
  fetchPage,
  columns,
  rowKey,
  reloadKey = 0,
  children,
  emptyTitle = "Aucun élément.",
  actions,
}: {
  title: string;
  description: string;
  fetchPage: (page: number, pageSize: number) => Promise<Page<T>>;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  reloadKey?: number;
  children?: ReactNode;
  emptyTitle?: string;
  actions?: ReactNode;
}) {
  const [page, setPage] = useState(1);
  const { data, error, isLoading, isRefreshing, retry } = useAsyncData(
    () => fetchPage(page, PAGE_SIZE),
    [page, reloadKey],
  );

  const tableColumns: TableColumn<T>[] = columns.map((column, index) => ({
    key: column.header,
    header: column.header,
    align: column.align,
    mobile: column.mobile ?? (index === 0 ? "title" : undefined),
    cell: column.render,
  }));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={title} description={description} actions={actions} />

      {children}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <TableSkeleton />}

      {data && (
        <>
          <p className="text-sm text-slate-600" aria-live="polite">
            {data.total} résultat{data.total > 1 ? "s" : ""}
            {isRefreshing && " — actualisation..."}
          </p>
          <DataTable
            caption={title}
            columns={tableColumns}
            rows={data.items}
            rowKey={rowKey}
            empty={<EmptyState title={emptyTitle} />}
          />
          <Pager page={data.page} totalPages={data.total_pages} onPage={(next) => setPage(Math.max(1, next))} />
        </>
      )}
    </div>
  );
}
