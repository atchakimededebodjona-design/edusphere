"use client";

import { useCallback, useEffect, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { formatDateFR } from "@/lib/format/date";
import { enrollments, type EnrollmentStatus, type StudentEnrollment } from "@/lib/students/client";

const STATUS_LABELS: Record<EnrollmentStatus, string> = {
  ACTIVE: "Active",
  WITHDRAWN: "Retirée",
  TRANSFERRED: "Transférée",
  COMPLETED: "Terminée",
};

export function StudentEnrollments({ studentId, schoolId, canManage }: { studentId: string; schoolId: string; canManage: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [items, setItems] = useState<StudentEnrollment[] | null>(null);
  const [classId, setClassId] = useState("");
  const [enrollmentDate, setEnrollmentDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    setLoadError(null);
    Promise.all([schoolClasses.list(schoolId), academicYears.list(schoolId), enrollments.list(studentId)])
      .then(([classesResult, yearsResult, itemsResult]) => {
        setClasses(classesResult);
        setYears(yearsResult);
        setItems(itemsResult);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId, studentId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!classId || !enrollmentDate) return;
    setBusy(true);
    setError(null);
    try {
      const created = await enrollments.create(studentId, { class_id: classId, enrollment_date: enrollmentDate });
      setItems((prev) => [...(prev ?? []), created]);
      setClassId("");
      setEnrollmentDate("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStatusChange(enrollmentId: string, status: EnrollmentStatus) {
    setBusy(true);
    setError(null);
    try {
      const updated = await enrollments.updateStatus(enrollmentId, status);
      setItems((prev) => (prev ?? []).map((e) => (e.id === updated.id ? updated : e)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadAll} />;
  if (classes === null || years === null || items === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  const className = (classIdValue: string) => classes.find((c) => c.id === classIdValue)?.name ?? "—";
  const yearName = (yearId: string) => years.find((y) => y.id === yearId)?.name ?? "—";

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Inscriptions</h2>

      {items.length === 0 ? (
        <p className="text-sm text-slate-400" data-testid="enrollments-empty">
          Aucune inscription.
        </p>
      ) : (
        <>
          {/* Desktop/tablette : tableau. Mobile : cartes empilées (voir ci-dessous). */}
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[640px] text-left text-sm" data-testid="enrollments-table">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                  <th className="px-3 py-2 font-medium">Classe</th>
                  <th className="px-3 py-2 font-medium">Année scolaire</th>
                  <th className="px-3 py-2 font-medium">Date d&apos;inscription</th>
                  <th className="px-3 py-2 font-medium">Statut</th>
                  {canManage && <th className="px-3 py-2 font-medium">Action</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id} className="border-b border-slate-100" data-testid="enrollment-row">
                    <td className="px-3 py-2">{className(e.class_id)}</td>
                    <td className="px-3 py-2">{yearName(e.academic_year_id)}</td>
                    <td className="px-3 py-2">{formatDateFR(e.enrollment_date)}</td>
                    <td className="px-3 py-2">
                      {!canManage && <span className="text-slate-700">{STATUS_LABELS[e.status]}</span>}
                    </td>
                    {canManage && (
                      <td className="px-3 py-2">
                        <label className="sr-only" htmlFor={`enrollment-status-${e.id}`}>
                          Statut de l&apos;inscription {className(e.class_id)}
                        </label>
                        <select
                          id={`enrollment-status-${e.id}`}
                          value={e.status}
                          onChange={(ev) => handleStatusChange(e.id, ev.target.value as EnrollmentStatus)}
                          disabled={busy}
                          className="rounded border border-slate-300 px-2 py-1 text-xs"
                        >
                          {Object.entries(STATUS_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 sm:hidden">
            {items.map((e) => (
              <div key={e.id} className="rounded border border-slate-200 p-3 text-sm" data-testid="enrollment-card">
                <p className="font-medium text-slate-900">{className(e.class_id)}</p>
                <p className="text-slate-500">{yearName(e.academic_year_id)}</p>
                <p className="text-slate-500">Inscrit le {formatDateFR(e.enrollment_date)}</p>
                {canManage ? (
                  <label className="mt-2 flex flex-col gap-1 text-xs text-slate-600">
                    Statut
                    <select
                      value={e.status}
                      onChange={(ev) => handleStatusChange(e.id, ev.target.value as EnrollmentStatus)}
                      disabled={busy}
                      className="rounded border border-slate-300 px-2 py-1 text-sm"
                    >
                      {Object.entries(STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">{STATUS_LABELS[e.status]}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Classe
            <select
              value={classId}
              onChange={(e) => setClassId(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Date d&apos;inscription
            <input
              type="date"
              value={enrollmentDate}
              onChange={(e) => setEnrollmentDate(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Inscrire
          </button>
        </form>
      )}
      {error && (
        <p className="text-sm text-red-700" data-testid="enrollment-error">
          {error}
        </p>
      )}
    </div>
  );
}
