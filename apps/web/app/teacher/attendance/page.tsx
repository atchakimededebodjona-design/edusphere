"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { attendanceRecords, attendanceSessions, type AttendanceStatusValue } from "@/lib/attendance/client";
import { academicTerms } from "@/lib/academics/client";
import { describeTeacherError, teacherApi, type TeacherAttendanceSession, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Vue simplifiée de l'appel. Les classes proposées sont celles du backend (affectations de
// l'enseignant). La création de session et l'enregistrement passent par les endpoints existants,
// qui refusent déjà toute classe non affectée ; une session verrouillée ne se modifie plus ici
// (le déverrouillage reste administratif).
const STATUS_LABELS: Record<AttendanceStatusValue, string> = { PRESENT: "Présent", ABSENT: "Absent", LATE: "Retard" };

function TeacherAttendancePageContent() {
  const searchParams = useSearchParams();
  const [classes, setClasses] = useState<TeacherClass[] | null>(null);
  const [classId, setClassId] = useState(searchParams.get("class_id") ?? "");
  const [termId, setTermId] = useState("");
  const [terms, setTerms] = useState<{ id: string; name: string }[]>([]);
  const [sessionDate, setSessionDate] = useState(new Date().toISOString().slice(0, 10));
  const [sessions, setSessions] = useState<TeacherAttendanceSession[]>([]);
  const [activeSession, setActiveSession] = useState<TeacherAttendanceSession | null>(null);
  const [students, setStudents] = useState<TeacherStudent[]>([]);
  const [statuses, setStatuses] = useState<Record<string, { status: AttendanceStatusValue; justified: boolean; reason: string }>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedClass = useMemo(() => classes?.find((c) => c.id === classId) ?? null, [classes, classId]);

  useEffect(() => {
    teacherApi.classes().then((list) => {
      setClasses(list);
      if (!classId && list[0]) setClassId(list[0].id);
    }).catch((err) => setError(describeTeacherError(err)));
    // classId initial uniquement
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedClass) return;
    academicTerms.list(selectedClass.academic_year_id).then((list) => {
      setTerms(list.map((t) => ({ id: t.id, name: t.name })));
      setTermId(list[0]?.id ?? "");
    }).catch(() => setTerms([]));
    teacherApi.students({ classId: selectedClass.id }).then(setStudents).catch((err) => setError(describeTeacherError(err)));
    teacherApi.attendanceSessions(selectedClass.id).then(setSessions).catch((err) => setError(describeTeacherError(err)));
    setActiveSession(null);
  }, [selectedClass]);

  async function createSession() {
    if (!selectedClass || !termId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const created = await attendanceSessions.create({ class_id: selectedClass.id, academic_term_id: termId, session_date: sessionDate });
      const entry: TeacherAttendanceSession = { id: created.id, class_id: created.class_id, academic_term_id: created.academic_term_id, session_date: created.session_date, locked: created.locked, taken_by: created.taken_by };
      setSessions((prev) => [entry, ...prev]);
      setActiveSession(entry);
      setStatuses(Object.fromEntries(students.map((s) => [s.id, { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" }])));
    } catch (err) {
      setError(describeTeacherError(err));
    } finally {
      setBusy(false);
    }
  }

  async function openSession(session: TeacherAttendanceSession) {
    setActiveSession(session);
    setError(null);
    setMessage(null);
    try {
      const records = await attendanceRecords.list(session.id);
      const byStudent = Object.fromEntries(records.map((r) => [r.student_id, r]));
      setStatuses(
        Object.fromEntries(
          students.map((s) => {
            const r = byStudent[s.id];
            return [s.id, { status: r?.status ?? "PRESENT", justified: r?.justified ?? false, reason: r?.reason ?? "" }];
          }),
        ),
      );
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  async function saveRoll() {
    if (!activeSession) return;
    setBusy(true);
    setError(null);
    try {
      await attendanceRecords.submit(
        activeSession.id,
        students.map((s) => {
          const entry = statuses[s.id];
          return {
            student_id: s.id,
            status: entry?.status ?? "PRESENT",
            justified: entry?.justified ?? false,
            reason: entry?.reason ? entry.reason : null,
          };
        }),
      );
      setMessage("Appel enregistré.");
    } catch (err) {
      setError(describeTeacherError(err));
    } finally {
      setBusy(false);
    }
  }

  if (classes === null && !error) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (classes && classes.length === 0) return <p className="text-sm text-slate-500">Aucune classe ne vous est affectée.</p>;

  const locked = activeSession?.locked ?? false;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Présences</h1>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          Classe
          <select value={classId} onChange={(e) => setClassId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {(classes ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Date
          <input type="date" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)} className="rounded border border-slate-300 px-2 py-2" />
        </label>
        <label className="flex flex-col gap-1">
          Période
          <select value={termId} onChange={(e) => setTermId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {terms.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={createSession} disabled={busy || !termId} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">
          Créer la session
        </button>
      </div>

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Sessions de la classe</h2>
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-400">Aucune session pour cette classe.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {sessions.map((s) => (
              <li key={s.id}>
                <button type="button" onClick={() => openSession(s)} className="text-slate-900 underline">
                  {s.session_date}
                </button>
                {s.locked && <span className="ml-2 text-xs text-slate-500">verrouillée</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {activeSession && (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Appel du {activeSession.session_date}</h2>
          {locked && <p className="mb-3 text-sm text-amber-700">Session verrouillée : seule l&apos;administration peut la déverrouiller.</p>}
          {students.length === 0 ? (
            <p className="text-sm text-slate-400">Aucun élève dans cette classe.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {students.map((s) => {
                const entry = statuses[s.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
                return (
                  <li key={s.id} className="flex flex-wrap items-center gap-3 border-b border-slate-100 pb-2 text-sm last:border-b-0">
                    <span className="min-w-[10rem]">{s.last_name} {s.first_name}</span>
                    <select
                      aria-label={`Statut de ${s.last_name}`}
                      disabled={locked}
                      value={entry.status}
                      onChange={(e) =>
                        setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, status: e.target.value as AttendanceStatusValue } }))
                      }
                      className="rounded border border-slate-300 px-2 py-1"
                    >
                      {(Object.keys(STATUS_LABELS) as AttendanceStatusValue[]).map((v) => (
                        <option key={v} value={v}>{STATUS_LABELS[v]}</option>
                      ))}
                    </select>
                    {entry.status === "ABSENT" && (
                      <>
                        <label className="flex items-center gap-1 text-xs">
                          <input
                            type="checkbox"
                            disabled={locked}
                            checked={entry.justified}
                            onChange={(e) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, justified: e.target.checked } }))}
                          />
                          Justifiée
                        </label>
                        <input
                          type="text"
                          placeholder="Motif (optionnel)"
                          aria-label={`Motif de ${s.last_name}`}
                          disabled={locked}
                          value={entry.reason}
                          onChange={(e) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, reason: e.target.value } }))}
                          className="min-w-[10rem] flex-1 rounded border border-slate-300 px-2 py-1 text-xs"
                        />
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <button type="button" onClick={saveRoll} disabled={busy || locked || students.length === 0} className="mt-4 rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50">
            Enregistrer l&apos;appel
          </button>
        </section>
      )}
    </div>
  );
}

export default function TeacherAttendancePage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-400">Chargement...</p>}>
      <TeacherAttendancePageContent />
    </Suspense>
  );
}
