"use client";

import { useCallback, useEffect, useState } from "react";
import { TabSkeleton } from "@/app/parent/children/[id]/ChildAttendance";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Card, EmptyState, SectionTitle, StatCard } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import type { StudentAverages } from "@/lib/grades/client";
import { parentChildren } from "@/lib/parent/client";

function formatAverage(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

// Refonte, phase 2 (2026-11-23) : moyenne générale en tête, puis les moyennes par matière en lignes
// lisibles sur téléphone. Mêmes données qu'avant (GET /parent/children/{id}/grades).
export function ChildGrades({ studentId }: { studentId: string }) {
  const [averages, setAverages] = useState<StudentAverages | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setAverages(null);
    parentChildren
      .grades(studentId)
      .then(setAverages)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (averages === null) return <TabSkeleton />;

  if (averages.subject_averages.length === 0 && averages.term_averages.length === 0) {
    return <EmptyState icon="listChecks" title="Pas encore de notes" description="Aucune note disponible pour le moment." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="child-general-average" className="flex flex-col gap-3">
        <SectionTitle id="child-general-average" title="Moyenne générale" />
        {averages.term_averages.length === 0 ? (
          <p className="text-sm text-slate-600">Aucune moyenne générale disponible pour le moment.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {averages.term_averages.map((a) => (
              <StatCard
                key={a.id}
                icon="chart"
                label="Moyenne générale"
                value={formatAverage(a.average)}
                hint={a.rank ? `Rang ${a.rank}` : undefined}
              />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="child-subject-averages" className="flex flex-col gap-3">
        <SectionTitle id="child-subject-averages" title="Moyennes par matière" />
        {averages.subject_averages.length === 0 ? (
          <p className="text-sm text-slate-600">Aucune note disponible pour le moment.</p>
        ) : (
          <Card padded={false}>
            <ul className="divide-y divide-slate-100">
              {averages.subject_averages.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm">
                  <span className="font-display text-lg font-bold tabular-nums text-slate-900">{formatAverage(a.average)}</span>
                  <span className="text-slate-600">{a.rank ? `Rang ${a.rank}` : "Rang —"}</span>
                  {a.appreciation && <span className="w-full text-slate-700">{a.appreciation}</span>}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>
    </div>
  );
}
