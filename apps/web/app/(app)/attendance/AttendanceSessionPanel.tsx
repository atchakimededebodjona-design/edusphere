"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import { useCallback, useEffect, useMemo, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import {
  attendanceRecords,
  attendanceSessions,
  type AttendanceRecord,
  type AttendanceSession,
  type AttendanceStatusValue,
} from "@/lib/attendance/client";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { students as studentsClient, type Student } from "@/lib/students/client";

const STATUS_LABELS: Record<AttendanceStatusValue, string> = {
  PRESENT: "Présent",
  ABSENT: "Absent",
  LATE: "Retard",
};

type RowValue = { status: AttendanceStatusValue; justified: boolean; reason: string };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AttendanceSessionPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [sessionDate, setSessionDate] = useState(todayIso());

  const [sessionsForDay, setSessionsForDay] = useState<AttendanceSession[] | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);
  const [existingRecords, setExistingRecords] = useState<AttendanceRecord[] | null>(null);
  const [values, setValues] = useState<Record<string, RowValue>>({});

  const [creatingSession, setCreatingSession] = useState(false);
  const [saving, setSaving] = useState(false);
  const [togglingLock, setTogglingLock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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
    setError(null);
    if (!selectedClassId) return;
    void studentsClient
      .list(schoolId, { classId: selectedClassId })
      .then(setRoster)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) {
      void academicTerms
        .list(schoolClass.academic_year_id)
        .then(setTerms)
        .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
    }
  }, [selectedClassId, schoolId, classes]);

  useEffect(() => {
    setSessionsForDay(null);
    setSelectedSessionId("");
    setError(null);
    if (!selectedClassId || !selectedTermId || !sessionDate) return;
    void attendanceSessions
      .list(selectedClassId, { academicTermId: selectedTermId, dateFrom: sessionDate, dateTo: sessionDate })
      .then((rows) => {
        setSessionsForDay(rows);
        if (rows.length === 1) setSelectedSessionId(rows[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedClassId, selectedTermId, sessionDate]);

  useEffect(() => {
    setExistingRecords(null);
    setSaved(false);
    setError(null);
    if (!selectedSessionId || !roster) return;
    void attendanceRecords
      .list(selectedSessionId)
      .then((rows) => {
        setExistingRecords(rows);
        const initial: Record<string, RowValue> = {};
        for (const student of roster) {
          const row = rows.find((r) => r.student_id === student.id);
          initial[student.id] = {
            status: row?.status ?? "PRESENT",
            justified: row?.justified ?? false,
            reason: row?.reason ?? "",
          };
        }
        setValues(initial);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedSessionId, roster]);

  const sortedRoster = useMemo(() => (roster ?? []).slice().sort((a, b) => a.last_name.localeCompare(b.last_name)), [roster]);
  const selectedSession = sessionsForDay?.find((s) => s.id === selectedSessionId) ?? null;

  async function handleCreateSession() {
    setCreatingSession(true);
    setError(null);
    try {
      const created = await attendanceSessions.create({
        class_id: selectedClassId,
        academic_term_id: selectedTermId,
        session_date: sessionDate,
      });
      setSessionsForDay((prev) => [...(prev ?? []), created]);
      setSelectedSessionId(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreatingSession(false);
    }
  }

  function updateValue(studentId: string, patch: Partial<RowValue>) {
    setValues((prev) => ({ ...prev, [studentId]: { ...prev[studentId], ...patch } }));
  }

  async function handleSave() {
    if (!roster) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const entries = roster.map((student) => {
        const value = values[student.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
        return {
          student_id: student.id,
          status: value.status,
          justified: value.justified,
          reason: value.reason.trim() === "" ? null : value.reason,
        };
      });
      const saved = await attendanceRecords.submit(selectedSessionId, entries);
      setExistingRecords(saved);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleLock() {
    if (!selectedSession) return;
    setTogglingLock(true);
    setError(null);
    try {
      const updated = await attendanceSessions.setLocked(selectedSession.id, !selectedSession.locked);
      setSessionsForDay((prev) => (prev ?? []).map((s) => (s.id === updated.id ? updated : s)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setTogglingLock(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadClasses} />;
  if (classes === null) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
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
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Date
          <input
            type="date"
            value={sessionDate}
            onChange={(e) => setSessionDate(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
      </div>

      {selectedClassId && selectedTermId && sessionDate && (
        <div className="flex flex-col gap-4">
          {sessionsForDay === null ? (
            <p className="text-sm text-slate-600">Chargement des sessions...</p>
          ) : sessionsForDay.length === 0 ? (
            canManage && (
              <button
                type="button"
                onClick={handleCreateSession}
                disabled={creatingSession}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
              >
                {creatingSession ? "Création..." : "Faire l'appel"}
              </button>
            )
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              {sessionsForDay.length > 1 && (
                <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
                  Session
                  <select
                    value={selectedSessionId}
                    onChange={(e) => setSelectedSessionId(e.target.value)}
                    className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
                  >
                    <option value="">—</option>
                    {sessionsForDay.map((s, i) => (
                      <option key={s.id} value={s.id}>
                        Session {i + 1}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {canManage && sessionsForDay.length === 0 && (
                <button type="button" onClick={handleCreateSession} disabled={creatingSession} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
                  Nouvelle session
                </button>
              )}
            </div>
          )}

          {selectedSession && (
            <>
              <div className="flex items-center gap-3">
                <span className={`rounded px-2 py-1 text-xs font-medium ${selectedSession.locked ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                  {selectedSession.locked ? "Verrouillée" : "Ouverte"}
                </span>
                {canManage && (
                  <button
                    type="button"
                    onClick={handleToggleLock}
                    disabled={togglingLock}
                    className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {togglingLock ? "..." : selectedSession.locked ? "Déverrouiller" : "Verrouiller"}
                  </button>
                )}
              </div>

              {existingRecords === null || roster === null ? (
                <p className="text-sm text-slate-600">Chargement des présences...</p>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
                  <table className="min-w-full divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Élève</th>
                        <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Statut</th>
                        <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Justifié</th>
                        <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Motif</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {sortedRoster.map((student) => {
                        const value = values[student.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
                        return (
                          <tr key={student.id}>
                            <td className="px-3 py-2">
                              {student.last_name} {student.first_name}
                            </td>
                            <td className="px-3 py-2">
                              <select
                                value={value.status}
                                onChange={(e) => updateValue(student.id, { status: e.target.value as AttendanceStatusValue })}
                                disabled={!canManage}
                                className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
                              >
                                {(Object.keys(STATUS_LABELS) as AttendanceStatusValue[]).map((s) => (
                                  <option key={s} value={s}>
                                    {STATUS_LABELS[s]}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="px-3 py-2">
                              <input
                                type="checkbox"
                                checked={value.justified}
                                onChange={(e) => updateValue(student.id, { justified: e.target.checked })}
                                disabled={!canManage || value.status === "PRESENT"}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <input
                                value={value.reason}
                                onChange={(e) => updateValue(student.id, { reason: e.target.value })}
                                disabled={!canManage}
                                placeholder="Motif (optionnel)"
                                className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
                              />
                            </td>
                          </tr>
                        );
                      })}
                      {sortedRoster.length === 0 && (
                        <tr>
                          <td colSpan={4} className="px-3 py-4 text-center text-slate-600">
                            Aucun élève inscrit dans cette classe.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {canManage && sortedRoster.length > 0 && (
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving || selectedSession.locked}
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
                >
                  {saving ? "Enregistrement..." : "Enregistrer l'appel"}
                </button>
              )}
              {saved && <p className="text-sm text-green-700">Présences enregistrées.</p>}
            </>
          )}
        </div>
      )}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  );
}
