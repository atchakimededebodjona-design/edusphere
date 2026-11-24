"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { OutboxFailures } from "@/components/pwa/OutboxFailures";
import { TeacherFormSkeleton } from "@/components/teacher-shell/TeacherFormSkeleton";
import { ActionBar } from "@/components/ui/ActionBar";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField, controlClass } from "@/components/ui/Field";
import { Segmented, type SegmentTone } from "@/components/ui/Segmented";
import { Alert, Badge, Card, EmptyState, PageHeader } from "@/components/ui/Surface";
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
import { useReveal } from "@/components/ui/useReveal";
import { describeTeacherError, teacherApi, type TeacherAttendanceSession, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Vue simplifiée de l'appel. Les classes proposées sont celles du backend (affectations de
// l'enseignant). La création de session et l'enregistrement passent par les endpoints existants,
// qui refusent déjà toute classe non affectée ; une session verrouillée ne se modifie plus ici
// (le déverrouillage reste administratif).
//
// Phase 32, lot 2 — utilisable sans connexion : chaque création de séance et chaque appel passe
// par la boîte d'envoi (lib/offline/sync.ts::saveNow). Avec internet, rien ne change à l'écran ;
// sans, la saisie est gardée sur l'appareil et part automatiquement au retour du réseau.
//
// Refonte, phase 2 (2026-11-23) — présentation seulement : statut en boutons au pouce (vrais boutons
// radio), compteurs, bouton d'enregistrement collé en bas de l'écran. Même saisie, mêmes envois.
const STATUS_OPTIONS: { value: AttendanceStatusValue; label: string; tone: SegmentTone }[] = [
  { value: "PRESENT", label: "Présent", tone: "success" },
  { value: "ABSENT", label: "Absent", tone: "danger" },
  { value: "LATE", label: "Retard", tone: "warning" },
];

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
  // Refonte, phase 2 : la feuille d'appel ouverte est amenée à l'écran (sur téléphone, elle est sous la liste).
  const [reveal, setReveal] = useState(0);
  const rollRef = useReveal<HTMLElement>(reveal);

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

  if (classes === null && !error) return <TeacherFormSkeleton />;
  if (classes && classes.length === 0) {
    return <EmptyState icon="layers" title="Aucune classe" description="Aucune classe ne vous est affectée." />;
  }

  const locked = activeSession?.locked ?? false;
  const displayedSessions: SessionView[] = [...localSessions, ...sessions];
  const counts = students.reduce(
    (acc, s) => {
      const status = statuses[s.id]?.status ?? "PRESENT";
      acc[status] += 1;
      return acc;
    },
    { PRESENT: 0, ABSENT: 0, LATE: 0 } as Record<AttendanceStatusValue, number>,
  );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Présences" description="Choisissez la classe et la date, créez la session, puis faites l'appel." />
      <Card>
        <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField label="Classe" value={classId} onChange={(e) => setClassId(e.target.value)}>
            {(classes ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </SelectField>
          <TextField label="Date" type="date" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)} />
          <SelectField label="Période" value={termId} onChange={(e) => setTermId(e.target.value)}>
            {terms.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </SelectField>
          <Button
            onClick={() => void createSession().then(() => setReveal((n) => n + 1))}
            disabled={busy || !termId}
            icon="clipboard"
          >
            Créer la session
          </Button>
        </div>
      </Card>

      <OutboxFailures kind="attendance" />
      {error && <Alert tone="danger">{error}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}

      <section aria-labelledby="attendance-sessions" className="flex flex-col gap-2">
        <h2 id="attendance-sessions" className="text-lg font-bold text-slate-900">Sessions de la classe</h2>
        {displayedSessions.length === 0 ? (
          <p className="text-sm text-slate-600">Aucune session pour cette classe.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {displayedSessions.map((s) => {
              const state = entryStateFor(s);
              const current = activeSession?.id === s.id;
              return (
                <li key={s.id} className="flex flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      void openSession(s);
                      setReveal((n) => n + 1);
                    }}
                    aria-pressed={current}
                    className={`flex min-h-11 items-center gap-2 rounded-lg border px-3 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 sm:min-h-10 ${
                      current ? "border-primary-600 bg-primary-50 text-primary-800" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                    }`}
                  >
                    {frenchDate(s.session_date)}
                  </button>
                  {(s.locked || state) && (
                    <span className="flex flex-wrap gap-1">
                      {s.locked && <Badge>verrouillée</Badge>}
                      {state === "pending" && <Badge tone="warning">en attente d&apos;envoi</Badge>}
                      {state === "failed" && <Badge tone="danger">refusée par le serveur</Badge>}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {activeSession && (
        <section ref={rollRef} aria-labelledby="attendance-roll" className="flex scroll-mt-20 flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="attendance-roll" className="text-lg font-bold text-slate-900">
              Appel du {frenchDate(activeSession.session_date)}
            </h2>
            {students.length > 0 && rollLoaded && (
              <p className="flex flex-wrap gap-2 text-sm">
                <Badge tone="success">{counts.PRESENT} présent{counts.PRESENT > 1 ? "s" : ""}</Badge>
                <Badge tone="danger">{counts.ABSENT} absent{counts.ABSENT > 1 ? "s" : ""}</Badge>
                <Badge tone="warning">{counts.LATE} retard{counts.LATE > 1 ? "s" : ""}</Badge>
              </p>
            )}
          </div>
          {locked && <Alert tone="warning">Session verrouillée : seule l&apos;administration peut la déverrouiller.</Alert>}
          {students.length === 0 ? (
            <p className="text-sm text-slate-600">Aucun élève dans cette classe.</p>
          ) : (
            <Card padded={false}>
              <ul className="divide-y divide-slate-100">
                {students.map((s) => {
                  const entry = statuses[s.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
                  return (
                    <li key={s.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                      <span className="font-medium text-slate-900">
                        {s.last_name} {s.first_name}
                      </span>
                      <Segmented
                        label={`Statut de ${s.last_name} ${s.first_name}`}
                        name={`status-${s.id}`}
                        value={entry.status}
                        options={STATUS_OPTIONS}
                        disabled={locked || !rollLoaded}
                        onChange={(status) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, status } }))}
                        className="w-full sm:w-auto"
                      />
                      {entry.status === "ABSENT" && (
                        <div className="flex w-full flex-wrap items-center gap-3">
                          <label className="flex min-h-11 items-center gap-2 text-sm text-slate-800 sm:min-h-9">
                            <input
                              type="checkbox"
                              disabled={locked || !rollLoaded}
                              checked={entry.justified}
                              onChange={(e) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, justified: e.target.checked } }))}
                              className="h-5 w-5 rounded border-slate-400 accent-primary-600"
                            />
                            Justifiée
                          </label>
                          <input
                            type="text"
                            placeholder="Motif (optionnel)"
                            aria-label={`Motif de ${s.last_name} ${s.first_name}`}
                            disabled={locked || !rollLoaded}
                            value={entry.reason}
                            onChange={(e) => setStatuses((prev) => ({ ...prev, [s.id]: { ...entry, reason: e.target.value } }))}
                            className={`${controlClass} min-w-[12rem] flex-1 sm:w-auto`}
                          />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
          <ActionBar className="-mx-4 px-4 md:mx-0 md:rounded-xl md:border">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-700">
                {students.length} élève{students.length > 1 ? "s" : ""}
                {rollLoaded && counts.ABSENT + counts.LATE > 0
                  ? ` · ${counts.ABSENT} absent${counts.ABSENT > 1 ? "s" : ""}, ${counts.LATE} retard${counts.LATE > 1 ? "s" : ""}`
                  : ""}
              </p>
              <Button
                onClick={saveRoll}
                disabled={busy || locked || !rollLoaded || students.length === 0}
                icon="checkSquare"
                className="w-full sm:w-auto"
              >
                Enregistrer l&apos;appel
              </Button>
            </div>
          </ActionBar>
        </section>
      )}
    </div>
  );
}

export default function TeacherAttendancePage() {
  return (
    <Suspense fallback={<TeacherFormSkeleton />}>
      <TeacherAttendancePageContent />
    </Suspense>
  );
}
