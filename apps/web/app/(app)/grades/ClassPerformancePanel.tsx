"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import { useCallback, useEffect, useMemo, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { classPerformance, type ClassPerformance } from "@/lib/grades/client";
import { students as studentsClient, type Student } from "@/lib/students/client";

export function ClassPerformancePanel({ schoolId, canExport }: { schoolId: string; canExport: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);
  const [performance, setPerformance] = useState<ClassPerformance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const loadClasses = useCallback(() => {
    setLoadError(null);
    schoolClasses
      .list(schoolId)
      .then(setClasses)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId]);

  useEffect(() => {
    loadClasses();
  }, [loadClasses]);

  useEffect(() => {
    setSelectedTermId("");
    setTerms(null);
    setRoster(null);
    setPerformance(null);
    setError(null);
    if (!selectedClassId) return;
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) {
      void academicTerms
        .list(schoolClass.academic_year_id)
        .then(setTerms)
        .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
    }
    void studentsClient
      .list(schoolId, { classId: selectedClassId })
      .then(setRoster)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedClassId, classes, schoolId]);

  useEffect(() => {
    setPerformance(null);
    setError(null);
    if (!selectedClassId || !selectedTermId) return;
    void classPerformance
      .get(selectedClassId, selectedTermId)
      .then(setPerformance)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedClassId, selectedTermId]);

  const rows = useMemo(() => {
    if (!performance || !roster) return [];
    return performance.students
      .map((entry) => ({ entry, student: roster.find((s) => s.id === entry.student_id) }))
      .sort((a, b) => (a.entry.rank ?? Infinity) - (b.entry.rank ?? Infinity));
  }, [performance, roster]);

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await classPerformance.exportXlsx(selectedClassId, selectedTermId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setExporting(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadClasses} />;
  if (classes === null) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Classe
          <select value={selectedClassId} onChange={(e) => setSelectedClassId(e.target.value)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500">
            <option value="">—</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Période
          <select
            value={selectedTermId}
            onChange={(e) => setSelectedTermId(e.target.value)}
            disabled={!terms}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">—</option>
            {terms?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {canExport && selectedClassId && selectedTermId && (
          <div className="flex flex-col justify-end gap-1">
            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={exporting}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
            >
              {exporting ? "Génération..." : "Exporter (.xlsx)"}
            </button>
          </div>
        )}
      </div>
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {exportError && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{exportError}</p>}

      {selectedClassId && selectedTermId && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Rang</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Élève</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Moyenne</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {performance === null ? (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-slate-600">
                    Chargement...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-slate-600">
                    Aucune moyenne disponible pour cette période.
                  </td>
                </tr>
              ) : (
                rows.map(({ entry, student }) => (
                  <tr key={entry.student_id}>
                    <td className="px-3 py-2">{entry.rank ?? "—"}</td>
                    <td className="px-3 py-2">
                      {student ? `${student.last_name} ${student.first_name}` : entry.student_id}
                    </td>
                    <td className="px-3 py-2">{entry.average ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
