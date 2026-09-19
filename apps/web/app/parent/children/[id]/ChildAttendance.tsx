"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { parentChildren, type ParentAttendanceSummary } from "@/lib/parent/client";

function formatRate(rate: number | null): string {
  return rate === null ? "Aucune donnée" : `${rate}%`;
}

export function ChildAttendance({ studentId }: { studentId: string }) {
  const [summary, setSummary] = useState<ParentAttendanceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setSummary(null);
    parentChildren
      .attendanceSummary(studentId)
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (summary === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Taux de présence" value={formatRate(summary.attendance_rate)} />
        <Metric label="Sessions totales" value={String(summary.total_sessions)} />
        <Metric label="Présences" value={String(summary.present_count)} />
        <Metric label="Absences" value={String(summary.absent_count)} />
        <Metric label="Retards" value={String(summary.late_count)} />
        <Metric label="Absences justifiées" value={String(summary.justified_absence_count)} />
      </div>
      {summary.total_sessions === 0 && (
        <p className="text-sm text-slate-400">Aucune session de présence enregistrée pour le moment.</p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-bold text-slate-900">{value}</p>
    </div>
  );
}
