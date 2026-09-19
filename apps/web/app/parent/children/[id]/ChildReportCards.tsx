"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import type { ReportCard } from "@/lib/report-cards/client";
import { parentChildren } from "@/lib/parent/client";

// Ne liste jamais un bulletin non publié : le backend lui-même ne les renvoie pas ici
// (parent/router.py::list_child_report_cards filtre `published_at IS NOT NULL`), rien à
// reproduire côté client.
export function ChildReportCards({ studentId, studentLabel }: { studentId: string; studentLabel: string }) {
  const [items, setItems] = useState<ReportCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setItems(null);
    parentChildren
      .reportCards(studentId)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDownload(reportCard: ReportCard) {
    setDownloadError(null);
    try {
      await parentChildren.downloadReportCardPdf(studentId, reportCard, studentLabel);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Le téléchargement a échoué.");
    }
  }

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (items === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      {downloadError && <p className="text-sm text-red-700">{downloadError}</p>}
      <ul className="flex flex-col gap-2">
        {items.map((rc) => (
          <li
            key={rc.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 bg-white px-4 py-3 text-sm"
          >
            <div>
              <p className="font-medium text-slate-900">
                Moyenne générale {rc.general_average ?? "—"} {rc.general_rank ? `— Rang ${rc.general_rank}` : ""}
              </p>
              <p className="text-xs text-slate-500">
                Publié le {new Date(rc.published_at ?? rc.generated_at).toLocaleDateString()}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleDownload(rc)}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              Télécharger le PDF
            </button>
          </li>
        ))}
        {items.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-400">
            Aucun bulletin publié pour le moment.
          </li>
        )}
      </ul>
    </div>
  );
}
