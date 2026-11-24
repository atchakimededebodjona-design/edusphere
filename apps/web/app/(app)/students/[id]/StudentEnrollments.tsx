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
  if (classes === null || years === null || items === null) return <p className="text-sm text-slate-600">Chargement...</p>;

  const className = (classIdValue: string) => classes.find((c) => c.id === classIdValue)?.name ?? "—";
  const yearName = (yearId: string) => years.find((y) => y.id === yearId)?.name ?? "—";

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <h2 className="text-lg font-bold text-slate-900">Inscriptions</h2>

      {items.length === 0 ? (
        <p className="text-sm text-slate-600" data-testid="enrollments-empty">
          Aucune inscription.
        </p>
      ) : (
        <>
          {/* Desktop/tablette : tableau. Mobile : cartes empilées (voir ci-dessous). */}
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[640px] text-left text-sm" data-testid="enrollments-table">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-600">
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
                          className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
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
              <div key={e.id} className="rounded-xl border border-slate-200 bg-white p-4 text-sm" data-testid="enrollment-card">
                <p className="font-medium text-slate-900">{className(e.class_id)}</p>
                <p className="text-slate-600">{yearName(e.academic_year_id)}</p>
                <p className="text-slate-600">Inscrit le {formatDateFR(e.enrollment_date)}</p>
                {canManage ? (
                  <label className="mt-2 flex flex-col gap-1 text-xs text-slate-600">
                    Statut
                    <select
                      value={e.status}
                      onChange={(ev) => handleStatusChange(e.id, ev.target.value as EnrollmentStatus)}
                      disabled={busy}
                      className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
                    >
                      {Object.entries(STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <p className="mt-1 text-xs text-slate-600">{STATUS_LABELS[e.status]}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Classe
            <select
              value={classId}
              onChange={(e) => setClassId(e.target.value)}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            >
              <option value="">—</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Date d&apos;inscription
            <input
              type="date"
              value={enrollmentDate}
              onChange={(e) => setEnrollmentDate(e.target.value)}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            />
          </label>
          <button type="submit" disabled={busy} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
            Inscrire
          </button>
        </form>
      )}
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="enrollment-error">
          {error}
        </p>
      )}
    </section>
  );
}
