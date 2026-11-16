"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { OutboxFailures } from "@/components/pwa/OutboxFailures";
import { attendanceRecords, type AttendanceRecordEntry, type AttendanceStatusValue } from "@/lib/attendance/client";
import { academicTerms } from "@/lib/academics/client";
import {
  attendanceKey,
  findOutboxEntry,
  newIdempotencyKey,
  OUTBOX_CHANGED_EVENT,
  type AttendanceOutboxEntry,
  type NewSession,
  type OutboxChange,
} from "@/lib/offline/outbox";
import { saveNow, type SaveOutcome } from "@/lib/offline/sync";
import { useOutbox } from "@/lib/offline/useOutbox";
import { describeTeacherError, teacherApi, type TeacherAttendanceSession, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Vue simplifiée de l'appel. Les classes proposées sont celles du backend (affectations de
// l'enseignant). La création de session et l'enregistrement passent par les endpoints existants,
// qui refusent déjà toute classe non affectée ; une session verrouillée ne se modifie plus ici
// (le déverrouillage reste administratif).
//
// Phase 32, lot 2 — utilisable sans connexion : chaque création de séance et chaque appel passe
// par la boîte d'envoi (lib/offline/sync.ts::saveNow). Avec internet, rien ne change à l'écran ;
// sans, la saisie est gardée sur l'appareil et part automatiquement au retour du réseau.
const STATUS_LABELS: Record<AttendanceStatusValue, string> = { PRESENT: "Présent", ABSENT: "Absent", LATE: "Retard" };

type RollEntry = { status: AttendanceStatusValue; justified: boolean; reason: string };
/** Séance du serveur, ou séance créée sur l'appareil et pas encore envoyée (`pendingCreate`). */
type SessionView = TeacherAttendanceSession & { pendingCreate?: NewSession };

const QUEUED_SESSION =
  "Hors connexion : la séance est créée sur cet appareil. Faites l'appel normalement, tout sera envoyé au retour d'internet.";
const QUEUED_ROLL = "Appel gardé sur cet appareil : il sera envoyé automatiquement au retour d'internet.";
const UNSAVED =
  "Hors connexion, et cet appareil ne peut pas garder la saisie (navigation privée ?). Réessayez quand internet sera revenu.";

function localSessionView(create: NewSession): SessionView {
  return {
    id: `local:${create.idempotency_key}`,
    class_id: create.class_id,
    academic_term_id: create.academic_term_id,
    session_date: create.session_date,
    locked: false,
    taken_by: null,
    pendingCreate: create,
  };
}

function frenchDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

function TeacherAttendancePageContent() {
  const searchParams = useSearchParams();
  const [classes, setClasses] = useState<TeacherClass[] | null>(null);
  const [classId, setClassId] = useState(searchParams.get("class_id") ?? "");
  const [termId, setTermId] = useState("");
  const [terms, setTerms] = useState<{ id: string; name: string }[]>([]);
  const [sessionDate, setSessionDate] = useState(new Date().toISOString().slice(0, 10));
  const [sessions, setSessions] = useState<TeacherAttendanceSession[]>([]);
  const [activeSession, setActiveSession] = useState<SessionView | null>(null);
  const [students, setStudents] = useState<TeacherStudent[]>([]);
  const [statuses, setStatuses] = useState<Record<string, RollEntry>>({});
  // Appel affiché réellement chargé pour la séance ouverte : sans lui, enregistrer écraserait
  // l'appel du serveur avec une feuille qui n'est pas la sienne.
  const [rollLoaded, setRollLoaded] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const outbox = useOutbox();

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

  // Une séance créée hors connexion vient d'être envoyée : liste rechargée, et la séance ouverte
  // prend son identifiant réel (l'appel en cours de saisie est conservé).
  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<OutboxChange>).detail;
      if (!detail?.sentKey?.startsWith("attendance:new:") || !detail.targetId) return;
      const targetId = detail.targetId;
      if (selectedClass) teacherApi.attendanceSessions(selectedClass.id).then(setSessions).catch(() => {});
      setActiveSession((prev) =>
        prev?.pendingCreate && attendanceKey({ create: prev.pendingCreate }) === detail.sentKey
          ? { ...prev, id: targetId, pendingCreate: undefined }
          : prev,
      );
    };
    window.addEventListener(OUTBOX_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(OUTBOX_CHANGED_EVENT, onChange);
  }, [selectedClass]);

  const classEntries = useMemo(
    () => outbox.filter((e): e is AttendanceOutboxEntry => e.kind === "attendance" && e.classId === classId),
    [outbox, classId],
  );
  const localSessions = useMemo(
    () =>
      classEntries
        .flatMap((e) => ("create" in e.session ? [localSessionView(e.session.create)] : []))
        .sort((a, b) => b.session_date.localeCompare(a.session_date)),
    [classEntries],
  );
  const entryStateFor = (session: SessionView) =>
    classEntries.find((e) => e.key === attendanceKey(session.pendingCreate ? { create: session.pendingCreate } : { id: session.id }))
      ?.state;

  function defaultRoll(): Record<string, RollEntry> {
    return Object.fromEntries(students.map((s) => [s.id, { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" }]));
  }

  function rollFrom(records: { student_id: string; status: AttendanceStatusValue; justified?: boolean; reason?: string | null }[]) {
    const byStudent = Object.fromEntries(records.map((r) => [r.student_id, r]));
    return Object.fromEntries(
      students.map((s) => {
        const r = byStudent[s.id];
        return [s.id, { status: r?.status ?? "PRESENT", justified: r?.justified ?? false, reason: r?.reason ?? "" }];
      }),
    ) as Record<string, RollEntry>;
  }

  function showOutcome(outcome: SaveOutcome, sentMessage: string | null, queuedMessage: string) {
    if (outcome.status === "sent") setMessage(sentMessage);
    else if (outcome.status === "queued") setMessage(queuedMessage);
    else if (outcome.status === "rejected") setError(outcome.message);
    else setError(UNSAVED);
  }

  async function createSession() {
    if (!selectedClass || !termId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const create: NewSession = {
      class_id: selectedClass.id,
      academic_term_id: termId,
      session_date: sessionDate,
      idempotency_key: newIdempotencyKey(),
    };
    const outcome = await saveNow({
      kind: "attendance",
      key: attendanceKey({ create }),
      classId: selectedClass.id,
      label: `Appel du ${frenchDate(sessionDate)} — ${selectedClass.name}`,
      session: { create },
      records: [],
    });
    setBusy(false);
    showOutcome(outcome, null, QUEUED_SESSION);
    if (outcome.status === "sent") {
      const entry: TeacherAttendanceSession = {
        id: outcome.targetId,
        class_id: create.class_id,
        academic_term_id: create.academic_term_id,
        session_date: create.session_date,
        locked: false,
        taken_by: null,
      };
      setSessions((prev) => [entry, ...prev.filter((s) => s.id !== entry.id)]);
      setActiveSession(entry);
    } else if (outcome.status === "queued") {
      setActiveSession(localSessionView(create));
    } else {
      return;
    }
    setStatuses(defaultRoll());
    setRollLoaded(true);
  }

  async function openSession(session: SessionView) {
    setActiveSession(session);
    setRollLoaded(false);
    setError(null);
    setMessage(null);
    // Un appel déjà saisi sur cet appareil et pas encore envoyé prime sur celui du serveur.
    const pending = await findOutboxEntry(attendanceKey(session.pendingCreate ? { create: session.pendingCreate } : { id: session.id }));
    if (pending?.kind === "attendance" && pending.records.length > 0) {
      setStatuses(rollFrom(pending.records));
      setRollLoaded(true);
      return;
    }
    if (session.pendingCreate) {
      setStatuses(defaultRoll());
      setRollLoaded(true);
      return;
    }
    try {
      setStatuses(rollFrom(await attendanceRecords.list(session.id)));
      setRollLoaded(true);
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  async function saveRoll() {
    if (!activeSession || !selectedClass) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const records: AttendanceRecordEntry[] = students.map((s) => {
      const entry = statuses[s.id];
      return {
        student_id: s.id,
        status: entry?.status ?? "PRESENT",
        justified: entry?.justified ?? false,
        reason: entry?.reason ? entry.reason : null,
      };
    });
    const session = activeSession.pendingCreate ? { create: activeSession.pendingCreate } : { id: activeSession.id };
    const outcome = await saveNow({
      kind: "attendance",
      key: attendanceKey(session),
      classId: selectedClass.id,
      label: `Appel du ${frenchDate(activeSession.session_date)} — ${selectedClass.name}`,
      session,
      records,
    });
    setBusy(false);
    showOutcome(outcome, "Appel enregistré.", QUEUED_ROLL);
    if (outcome.status === "sent" && activeSession.pendingCreate) {
      setActiveSession({ ...activeSession, id: outcome.targetId, pendingCreate: undefined });
      teacherApi.attendanceSessions(selectedClass.id).then(setSessions).catch(() => {});
    }
  }

  if (classes === null && !error) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (classes && classes.length === 0) return <p className="text-sm text-slate-500">Aucune classe ne vous est affectée.</p>;

  const locked = activeSession?.locked ?? false;
  const displayedSessions: SessionView[] = [...localSessions, ...sessions];

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

      <OutboxFailures kind="attendance" />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Sessions de la classe</h2>
        {displayedSessions.length === 0 ? (
          <p className="text-sm text-slate-400">Aucune session pour cette classe.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {displayedSessions.map((s) => {
              const state = entryStateFor(s);
              return (
                <li key={s.id}>
                  <button type="button" onClick={() => openSession(s)} className="text-slate-900 underline">
                    {s.session_date}
                  </button>
                  {s.locked && <span className="ml-2 text-xs text-slate-500">verrouillée</span>}
                  {state === "pending" && <span className="ml-2 text-xs text-amber-700">en attente d&apos;envoi</span>}
                  {state === "failed" && <span className="ml-2 text-xs text-red-700">refusée par le serveur</span>}
                </li>
              );
            })}
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
                      disabled={locked || !rollLoaded}
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
                            disabled={locked || !rollLoaded}
                            checked={entry.justified}
                            onChange={(e) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, justified: e.target.checked } }))}
                          />
                          Justifiée
                        </label>
                        <input
                          type="text"
                          placeholder="Motif (optionnel)"
                          aria-label={`Motif de ${s.last_name}`}
                          disabled={locked || !rollLoaded}
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
          <button
            type="button"
            onClick={saveRoll}
            disabled={busy || locked || !rollLoaded || students.length === 0}
            className="mt-4 rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
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
