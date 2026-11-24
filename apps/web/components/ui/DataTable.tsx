import { Fragment, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";

// Refonte, phase 3 (2026-11-24) — tableau commun des écrans de gestion.
// - Ordinateur et tablette : un vrai tableau, en-têtes en capitales, lignes séparées.
// - Téléphone (< 640 px) : CHAQUE LIGNE DEVIENT UNE CARTE. Le titre de la ligne en tête, puis les
//   valeurs deux par deux, chacune précédée de son libellé, et les actions sur toute la largeur.
// Une seule structure de tableau dans la page, jamais deux copies (table + cartes) : les tests et les
// lecteurs d'écran trouvent chaque ligne une seule fois. Les rôles ARIA (table, row, cell) sont posés
// explicitement : certains navigateurs les oublient quand l'affichage d'un tableau change.

export type Column<T> = {
  key: string;
  header: ReactNode;
  /** Libellé écrit devant la valeur sur téléphone (par défaut : l'en-tête, s'il est un texte). */
  label?: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  /**
   * Place sur téléphone :
   * - "title" : en tête de carte, en gras, sans libellé ;
   * - "lead" : petit élément posé avant le titre (case à cocher, photo) ;
   * - "full" : toute la largeur, sans libellé (actions, détails longs) ;
   * - "hidden" : non affichée.
   * Par défaut : une demi-largeur, avec son libellé.
   */
  mobile?: "title" | "lead" | "full" | "hidden";
  /** En-tête gardé sur téléphone (case « Tout sélectionner »). */
  headerOnMobile?: boolean;
};

const MOBILE_CELL: Record<NonNullable<Column<unknown>["mobile"]> | "default", string> = {
  // `order-first` : le titre (et ce qui le précède) ouvre la carte même s'il n'est pas la première colonne
  // du tableau sur ordinateur.
  title: "max-sm:order-first max-sm:block max-sm:grow max-sm:basis-[60%] max-sm:text-base max-sm:font-semibold max-sm:text-slate-900",
  lead: "max-sm:order-first max-sm:block max-sm:shrink-0",
  full: "max-sm:block max-sm:w-full",
  hidden: "max-sm:hidden",
  // Libellé écrit par le CSS (`data-label`) : il ne s'ajoute pas au texte de la cellule, que les tests
  // et les copier-coller lisent tel quel ; les lecteurs d'écran l'annoncent.
  default:
    "max-sm:block max-sm:w-[calc(50%-0.5rem)] max-sm:before:mb-0.5 max-sm:before:block max-sm:before:text-xs " +
    "max-sm:before:font-medium max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]",
};

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  empty,
  rowTestId,
  rowTone,
  after,
  testId,
}: {
  /** Nom du tableau, annoncé par les lecteurs d'écran. */
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Affiché à la place du tableau quand il n'y a aucune ligne. */
  empty?: ReactNode;
  rowTestId?: (row: T) => string | undefined;
  /** Fond d'une ligne à signaler (non lue, annulée…). */
  rowTone?: (row: T) => "highlight" | "muted" | undefined;
  /** Panneau ouvert sous une ligne (photo d'un membre du personnel…). */
  after?: (row: T) => ReactNode;
  testId?: string;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  const mobileHeader = columns.some((c) => c.headerOnMobile);

  return (
    <div className="rounded-xl border border-slate-200 bg-white sm:overflow-x-auto">
      <table role="table" data-testid={testId} className="w-full text-sm max-sm:block">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup" className={`bg-slate-50 ${mobileHeader ? "max-sm:block max-sm:border-b max-sm:border-slate-200" : "max-sm:hidden"}`}>
          <tr role="row" className="max-sm:flex max-sm:items-center max-sm:gap-3 max-sm:px-4 max-sm:py-2">
            {columns.map((c) => (
              <th
                role="columnheader"
                scope="col"
                key={c.key}
                className={`text-xs font-semibold uppercase tracking-wide text-slate-600 sm:px-3 sm:py-2.5 ${
                  c.align === "right" ? "sm:text-right" : "text-left"
                } ${c.headerOnMobile ? "max-sm:block max-sm:normal-case max-sm:tracking-normal" : "max-sm:hidden"}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="divide-y divide-slate-200 max-sm:block">
          {rows.map((row) => {
            const extra = after?.(row);
            const tone = rowTone?.(row);
            return (
              <Fragment key={rowKey(row)}>
                <tr
                  role="row"
                  data-testid={rowTestId?.(row)}
                  className={`max-sm:flex max-sm:flex-wrap max-sm:items-start max-sm:gap-x-4 max-sm:gap-y-3 max-sm:p-4 ${
                    tone === "highlight" ? "bg-primary-50/50" : tone === "muted" ? "bg-slate-50 text-slate-600" : "sm:hover:bg-slate-50"
                  }`}
                >
                  {columns.map((c) => {
                    const label = c.label ?? (typeof c.header === "string" ? c.header : undefined);
                    const place = c.mobile ?? "default";
                    return (
                      <td
                        role="cell"
                        key={c.key}
                        data-label={place === "default" ? label : undefined}
                        className={`min-w-0 sm:px-3 sm:py-2.5 sm:align-middle ${c.align === "right" ? "sm:text-right sm:tabular-nums" : ""} ${MOBILE_CELL[place]}`}
                      >
                        {c.cell(row)}
                      </td>
                    );
                  })}
                </tr>
                {extra && (
                  <tr role="row" className="max-sm:block">
                    <td role="cell" colSpan={columns.length} className="bg-slate-50 px-4 py-4 max-sm:block sm:px-3">
                      {extra}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Pages précédente / suivante sous un tableau paginé. */
export function Pager({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex items-center justify-center gap-3 text-sm">
      <Button variant="secondary" icon="chevronLeft" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Précédent
      </Button>
      <span className="text-slate-700" aria-current="page">
        Page {page} / {totalPages}
      </span>
      <Button variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        Suivant
      </Button>
    </nav>
  );
}

/** Lignes grises animées pendant le premier chargement d'une liste. */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4" aria-busy="true" aria-label="Chargement">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} aria-hidden="true" className="h-5 w-full animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
      ))}
    </div>
  );
}
