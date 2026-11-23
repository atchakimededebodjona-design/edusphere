"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { EmptyState, Skeleton, StatCard } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { parentChildren, type ParentAttendanceSummary } from "@/lib/parent/client";

function formatRate(rate: number | null): string {
  return rate === null ? "Aucune donnée" : `${rate}%`;
}

export function TabSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-busy="true" aria-label="Chargement">
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-20 w-full rounded-xl" />
      ))}
    </div>
  );
}

// Refonte, phase 2 (2026-11-23) : mêmes chiffres, en cartes lisibles d'un coup d'œil.
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
  if (summary === null) return <TabSkeleton />;

  if (summary.total_sessions === 0) {
    return (
      <EmptyState
        icon="clipboard"
        title="Pas encore d'appel"
        description="Aucune session de présence enregistrée pour le moment."
      />
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <StatCard icon="chart" label="Taux de présence" value={formatRate(summary.attendance_rate)} />
      <StatCard icon="clipboard" label="Sessions totales" value={String(summary.total_sessions)} />
      <StatCard icon="checkSquare" tone="success" label="Présences" value={String(summary.present_count)} />
      <StatCard
        icon="user"
        tone={summary.absent_count > 0 ? "danger" : "success"}
        label="Absences"
        value={String(summary.absent_count)}
      />
      <StatCard icon="clock" tone={summary.late_count > 0 ? "warning" : "success"} label="Retards" value={String(summary.late_count)} />
      <StatCard icon="fileText" label="Absences justifiées" value={String(summary.justified_absence_count)} />
    </div>
  );
}
