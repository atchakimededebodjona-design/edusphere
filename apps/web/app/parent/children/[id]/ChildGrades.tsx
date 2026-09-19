"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import type { StudentAverages } from "@/lib/grades/client";
import { parentChildren } from "@/lib/parent/client";

function formatAverage(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

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
  if (averages === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Moyennes par matière</h3>
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Moyenne</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Rang</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Appréciation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {averages.subject_averages.map((a) => (
                <tr key={a.id}>
                  <td className="px-3 py-2 text-right">{formatAverage(a.average)}</td>
                  <td className="px-3 py-2 text-right">{a.rank ?? "—"}</td>
                  <td className="px-3 py-2">{a.appreciation ?? "—"}</td>
                </tr>
              ))}
              {averages.subject_averages.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-slate-400">
                    Aucune note disponible pour le moment.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Moyenne générale</h3>
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Moyenne</th>
                <th className="px-3 py-2 text-right font-medium text-slate-600">Rang</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {averages.term_averages.map((a) => (
                <tr key={a.id}>
                  <td className="px-3 py-2 text-right">{formatAverage(a.average)}</td>
                  <td className="px-3 py-2 text-right">{a.rank ?? "—"}</td>
                </tr>
              ))}
              {averages.term_averages.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-3 py-4 text-center text-slate-400">
                    Aucune moyenne générale disponible pour le moment.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
