"use client";

import { useCallback, useEffect, useState } from "react";
import { TabSkeleton } from "@/app/parent/children/[id]/ChildAttendance";
import { Button } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Alert, EmptyState } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import type { ReportCard } from "@/lib/report-cards/client";
import { parentChildren } from "@/lib/parent/client";

// Ne liste jamais un bulletin non publié : le backend lui-même ne les renvoie pas ici
// (parent/router.py::list_child_report_cards filtre `published_at IS NOT NULL`), rien à
// reproduire côté client. Refonte, phase 2 (2026-11-23) : présentation.
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
  if (items === null) return <TabSkeleton />;
  if (items.length === 0) {
    return <EmptyState icon="fileText" title="Pas encore de bulletin" description="Aucun bulletin publié pour le moment." />;
  }

  return (
    <div className="flex flex-col gap-3">
      {downloadError && <Alert tone="danger">{downloadError}</Alert>}
      <ul className="flex flex-col gap-3">
        {items.map((rc) => (
          <li
            key={rc.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm"
          >
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">
                Moyenne générale {rc.general_average ?? "—"} {rc.general_rank ? `— Rang ${rc.general_rank}` : ""}
              </p>
              <p className="text-xs text-slate-600">
                Publié le {new Date(rc.published_at ?? rc.generated_at).toLocaleDateString("fr-FR")}
              </p>
            </div>
            <Button variant="secondary" size="sm" icon="fileText" onClick={() => void handleDownload(rc)}>
              Télécharger le PDF
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
