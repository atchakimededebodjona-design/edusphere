"use client";

import { useEffect, useState } from "react";
import { schoolClasses, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { enrollments, type EnrollmentStatus, type StudentEnrollment } from "@/lib/students/client";

const STATUS_LABELS: Record<EnrollmentStatus, string> = {
  ACTIVE: "Active",
  WITHDRAWN: "Retirée",
  TRANSFERRED: "Transférée",
  COMPLETED: "Terminée",
};

export function StudentEnrollments({ studentId, schoolId, canManage }: { studentId: string; schoolId: string; canManage: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [items, setItems] = useState<StudentEnrollment[] | null>(null);
  const [classId, setClassId] = useState("");
  const [enrollmentDate, setEnrollmentDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void schoolClasses.list(schoolId).then(setClasses);
    void enrollments.list(studentId).then(setItems);
  }, [schoolId, studentId]);

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

  if (classes === null || items === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Inscriptions</h2>
      <ul className="flex flex-col gap-1">
        {items.map((e) => (
          <li key={e.id} className="flex items-center justify-between rounded border border-slate-200 px-3 py-1.5 text-sm">
            <span>
              {classes.find((c) => c.id === e.class_id)?.name ?? e.class_id} — inscrit le {e.enrollment_date}
            </span>
            {canManage ? (
              <select
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
            ) : (
              <span className="text-xs text-slate-500">{STATUS_LABELS[e.status]}</span>
            )}
          </li>
        ))}
        {items.length === 0 && <li className="text-sm text-slate-400">Aucune inscription.</li>}
      </ul>

      {canManage && (
        <form onSubmit={handleCreate} className="flex items-end gap-3 rounded border border-dashed border-slate-300 p-3">
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
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
