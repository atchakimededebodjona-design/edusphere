"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { academicTerms } from "@/lib/academics/client";
import {
  assessmentTypes,
  classPerformance,
  results,
  studentAverages,
  type AssessmentType,
} from "@/lib/grades/client";
import { OutboxFailures } from "@/components/pwa/OutboxFailures";
import {
  findOutboxEntry,
  gradesKey,
  newIdempotencyKey,
  OUTBOX_CHANGED_EVENT,
  type GradesOutboxEntry,
  type NewAssessment,
  type OutboxChange,
} from "@/lib/offline/outbox";
import { saveNow, type SaveOutcome } from "@/lib/offline/sync";
import { useOutbox } from "@/lib/offline/useOutbox";
import { describeTeacherError, teacherApi, type TeacherAssessment, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Notes & évaluations du portail. Les matières proposées sont uniquement celles de l'enseignant
// (TeacherAssignment). La création d'évaluation et la saisie passent par les endpoints existants,
// qui refusent déjà toute matière non affectée (contrôle backend, vérifié dans les tests).
//
// Phase 32, lot 2 — utilisable sans connexion : création d'évaluation et saisie des notes passent
// par la boîte d'envoi (lib/offline/sync.ts::saveNow), comme l'appel (voir teacher/attendance).

/** Évaluation du serveur, ou créée sur l'appareil et pas encore envoyée (`pendingCreate`). */
type AssessmentView = TeacherAssessment & { pendingCreate?: NewAssessment };

const QUEUED_ASSESSMENT = "Hors connexion : évaluation créée sur cet appareil. Elle sera envoyée au retour d'internet.";
const QUEUED_SCORES = "Notes gardées sur cet appareil : elles seront envoyées automatiquement au retour d'internet.";
const UNSAVED =
  "Hors connexion, et cet appareil ne peut pas garder la saisie (navigation privée ?). Réessayez quand internet sera revenu.";

function localAssessmentView(create: NewAssessment, subjectName: string): AssessmentView {
  return {
    id: `local:${create.idempotency_key}`,
    name: create.name,
    class_subject_id: create.class_subject_id,
    subject_name: subjectName,
    academic_term_id: create.academic_term_id,
    max_score: create.max_score ?? 20,
    assessment_date: create.assessment_date,
    pendingCreate: create,
  };
}

function TeacherGradesPageContent() {
  const searchParams = useSearchParams();
  const [classes, setClasses] = useState<TeacherClass[] | null>(null);
  const [classId, setClassId] = useState(searchParams.get("class_id") ?? "");
  const [classSubjectId, setClassSubjectId] = useState("");
  const [terms, setTerms] = useState<{ id: string; name: string }[]>([]);
  const [termId, setTermId] = useState("");
  const [types, setTypes] = useState<AssessmentType[]>([]);
  const [typeId, setTypeId] = useState("");
  const [assessments, setAssessments] = useState<TeacherAssessment[]>([]);
  const [students, setStudents] = useState<TeacherStudent[]>([]);
  const [activeAssessment, setActiveAssessment] = useState<AssessmentView | null>(null);
  const [scores, setScores] = useState<Record<string, { score: string; absent: boolean }>>({});
  // Notes affichées réellement chargées pour l'évaluation ouverte (sinon, enregistrer écraserait
  // celles du serveur avec une feuille qui n'est pas la sienne).
  const [scoresLoaded, setScoresLoaded] = useState(false);
  const outbox = useOutbox();
  const [form, setForm] = useState({ name: "", max_score: "20", assessment_date: new Date().toISOString().slice(0, 10) });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [averages, setAverages] = useState<Record<string, { subject: number | null; general: number | null; rank: number | null }>>({});

  const selectedClass = useMemo(() => classes?.find((c) => c.id === classId) ?? null, [classes, classId]);

  useEffect(() => {
    teacherApi.classes().then((list) => {
      setClasses(list);
      if (!classId && list[0]) setClassId(list[0].id);
    }).catch((err) => setError(describeTeacherError(err)));
    // initialisation unique
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedClass) return;
    setClassSubjectId(selectedClass.subjects[0]?.class_subject_id ?? "");
    academicTerms.list(selectedClass.academic_year_id).then((list) => {
      setTerms(list.map((t) => ({ id: t.id, name: t.name })));
      setTermId(list[0]?.id ?? "");
    }).catch(() => setTerms([]));
    assessmentTypes.list(selectedClass.school_id).then((list) => {
      setTypes(list);
      setTypeId(list[0]?.id ?? "");
    }).catch(() => setTypes([]));
    teacherApi.assessments(selectedClass.id).then(setAssessments).catch((err) => setError(describeTeacherError(err)));
    teacherApi.classStudents(selectedClass.id).then(setStudents).catch((err) => setError(describeTeacherError(err)));
    setActiveAssessment(null);
  }, [selectedClass]);

  // Une évaluation créée hors connexion vient d'être envoyée : liste rechargée, et l'évaluation
  // ouverte prend son identifiant réel (les notes en cours de saisie sont conservées).
  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<OutboxChange>).detail;
      if (!detail?.sentKey?.startsWith("grades:new:") || !detail.targetId) return;
      const targetId = detail.targetId;
      if (selectedClass) teacherApi.assessments(selectedClass.id).then(setAssessments).catch(() => {});
      setActiveAssessment((prev) =>
        prev?.pendingCreate && gradesKey({ create: prev.pendingCreate }) === detail.sentKey
          ? { ...prev, id: targetId, pendingCreate: undefined }
          : prev,
      );
    };
    window.addEventListener(OUTBOX_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(OUTBOX_CHANGED_EVENT, onChange);
  }, [selectedClass]);

  const classEntries = useMemo(
    () => outbox.filter((e): e is GradesOutboxEntry => e.kind === "grades" && e.classId === classId),
    [outbox, classId],
  );
  const localAssessments = useMemo(
    () =>
      classEntries.flatMap((e) => {
        if (!("create" in e.assessment)) return [];
        const create = e.assessment.create;
        const subject = selectedClass?.subjects.find((s) => s.class_subject_id === create.class_subject_id);
        return [localAssessmentView(create, subject?.subject_name ?? "")];
      }),
    [classEntries, selectedClass],
  );
  const entryStateFor = (assessment: AssessmentView) =>
    classEntries.find(
      (e) => e.key === gradesKey(assessment.pendingCreate ? { create: assessment.pendingCreate } : { id: assessment.id }),
    )?.state;

  function showOutcome(outcome: SaveOutcome, sentMessage: string, queuedMessage: string) {
    if (outcome.status === "sent") setMessage(sentMessage);
    else if (outcome.status === "queued") setMessage(queuedMessage);
    else if (outcome.status === "rejected") setError(outcome.message);
    else setError(UNSAVED);
  }

  // Moyennes : réutilise les calculs existants (grades/service.py), jamais recalculé côté
  // frontend. Moyenne générale + rang en un seul appel (classPerformance, déjà scopé enseignant) ;
  // moyenne par matière via l'endpoint par élève (seule source pour ce niveau de détail).
  useEffect(() => {
    if (!classId || !classSubjectId || !termId || students.length === 0) {
      setAverages({});
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [performance, perStudent] = await Promise.all([
          classPerformance.get(classId, termId).catch(() => null),
          Promise.all(
            students.map((s) =>
              studentAverages.get(s.id, termId).then(
                (a) => ({ studentId: s.id, subjectAverage: a.subject_averages.find((sa) => sa.class_subject_id === classSubjectId)?.average ?? null }),
                () => ({ studentId: s.id, subjectAverage: null as number | null }),
              ),
            ),
          ),
        ]);
        if (cancelled) return;
        const general = new Map((performance?.students ?? []).map((p) => [p.student_id, p]));
        setAverages(
          Object.fromEntries(
            perStudent.map(({ studentId, subjectAverage }) => [
              studentId,
              { subject: subjectAverage, general: general.get(studentId)?.average ?? null, rank: general.get(studentId)?.rank ?? null },
            ]),
          ),
        );
      } catch {
        if (!cancelled) setAverages({});
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classId, classSubjectId, termId, students]);

  async function createAssessment() {
    if (!selectedClass || !classSubjectId || !termId || !typeId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const create: NewAssessment = {
      class_subject_id: classSubjectId,
      academic_term_id: termId,
      assessment_type_id: typeId,
      name: form.name,
      max_score: Number(form.max_score),
      assessment_date: form.assessment_date,
      idempotency_key: newIdempotencyKey(),
    };
    const subjectName = selectedClass.subjects.find((s) => s.class_subject_id === classSubjectId)?.subject_name ?? "";
    const outcome = await saveNow({
      kind: "grades",
      key: gradesKey({ create }),
      classId: selectedClass.id,
      label: `Évaluation « ${create.name} » — ${subjectName}, ${selectedClass.name}`,
      assessment: { create },
      results: [],
    });
    setBusy(false);
    showOutcome(outcome, "Évaluation créée.", QUEUED_ASSESSMENT);
    if (outcome.status === "sent") {
      teacherApi.assessments(selectedClass.id).then(setAssessments).catch(() => {});
    }
    if (outcome.status === "sent" || outcome.status === "queued") setForm((f) => ({ ...f, name: "" }));
  }

  async function openAssessment(assessment: AssessmentView) {
    setActiveAssessment(assessment);
    setScoresLoaded(false);
    setError(null);
    setMessage(null);
    // Des notes déjà saisies sur cet appareil et pas encore envoyées priment sur celles du serveur.
    const pending = await findOutboxEntry(
      gradesKey(assessment.pendingCreate ? { create: assessment.pendingCreate } : { id: assessment.id }),
    );
    if (pending?.kind === "grades" && pending.results.length > 0) {
      setScores(
        Object.fromEntries(
          pending.results.map((r) => [r.student_id, { score: r.score == null ? "" : String(r.score), absent: r.is_absent ?? false }]),
        ),
      );
      setScoresLoaded(true);
      return;
    }
    if (assessment.pendingCreate) {
      setScores({});
      setScoresLoaded(true);
      return;
    }
    try {
      const list = await results.list(assessment.id);
      setScores(Object.fromEntries(list.map((r) => [r.student_id, { score: r.score == null ? "" : String(r.score), absent: r.is_absent }])));
      setScoresLoaded(true);
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  async function saveScores() {
    if (!activeAssessment || !selectedClass) return;
    setError(null);
    setMessage(null);
    // Contrôle avant l'envoi : hors connexion, une note invalide ne serait refusée qu'au retour
    // d'internet. L'API reste l'autorité (même règle côté serveur).
    const maxScore = activeAssessment.max_score;
    const invalid = students.find((s) => {
      const entry = scores[s.id];
      if (!entry || entry.absent || entry.score === "") return false;
      const value = Number(entry.score);
      return !Number.isFinite(value) || value < 0 || value > maxScore;
    });
    if (invalid) {
      setError(`La note de ${invalid.last_name} ${invalid.first_name} doit être comprise entre 0 et ${maxScore}.`);
      return;
    }
    setBusy(true);
    const assessment = activeAssessment.pendingCreate ? { create: activeAssessment.pendingCreate } : { id: activeAssessment.id };
    const outcome = await saveNow({
      kind: "grades",
      key: gradesKey(assessment),
      classId: selectedClass.id,
      label: `Notes « ${activeAssessment.name} » — ${activeAssessment.subject_name}, ${selectedClass.name}`,
      assessment,
      results: students.map((s) => {
        const entry = scores[s.id];
        return { student_id: s.id, score: entry?.absent || !entry?.score ? null : Number(entry.score), is_absent: entry?.absent ?? false };
      }),
    });
    setBusy(false);
    showOutcome(outcome, "Notes enregistrées.", QUEUED_SCORES);
    if (outcome.status === "sent" && activeAssessment.pendingCreate) {
      setActiveAssessment({ ...activeAssessment, id: outcome.targetId, pendingCreate: undefined });
      teacherApi.assessments(selectedClass.id).then(setAssessments).catch(() => {});
    }
  }

  if (classes === null && !error) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (classes && classes.length === 0) return <p className="text-sm text-slate-500">Aucune classe ne vous est affectée.</p>;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Notes &amp; évaluations</h1>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          Classe
          <select value={classId} onChange={(e) => setClassId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {(classes ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Matière
          <select value={classSubjectId} onChange={(e) => setClassSubjectId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {(selectedClass?.subjects ?? []).map((s) => <option key={s.class_subject_id} value={s.class_subject_id}>{s.subject_name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Période
          <select value={termId} onChange={(e) => setTermId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
      </div>

      <OutboxFailures kind="grades" />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">Créer une évaluation</h2>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <input placeholder="Nom de l'évaluation" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded border border-slate-300 px-2 py-2" />
          <select value={typeId} onChange={(e) => setTypeId(e.target.value)} className="rounded border border-slate-300 px-2 py-2">
            {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <input type="number" min="1" value={form.max_score} onChange={(e) => setForm({ ...form, max_score: e.target.value })} className="w-24 rounded border border-slate-300 px-2 py-2" aria-label="Note maximale" />
          <input type="date" value={form.assessment_date} onChange={(e) => setForm({ ...form, assessment_date: e.target.value })} className="rounded border border-slate-300 px-2 py-2" />
          <button type="button" onClick={createAssessment} disabled={busy || !form.name || !classSubjectId || !termId || !typeId} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">
            Créer
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Évaluations</h2>
        {localAssessments.length + assessments.length === 0 ? (
          <p className="text-sm text-slate-400">Aucune évaluation pour cette classe.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {[...localAssessments, ...assessments].map((a: AssessmentView) => {
              const state = entryStateFor(a);
              return (
                <li key={a.id}>
                  <button type="button" onClick={() => openAssessment(a)} className="text-slate-900 underline">
                    {a.name} — {a.subject_name} ({a.assessment_date}, /{a.max_score})
                  </button>
                  {state === "pending" && <span className="ml-2 text-xs text-amber-700">en attente d&apos;envoi</span>}
                  {state === "failed" && <span className="ml-2 text-xs text-red-700">refusée par le serveur</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">
          Moyennes — {terms.find((t) => t.id === termId)?.name ?? "période"}
        </h2>
        {students.length === 0 ? (
          <p className="text-sm text-slate-400">Aucun élève dans cette classe.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-4">Élève</th>
                  <th className="py-1 pr-4">Moyenne matière</th>
                  <th className="py-1 pr-4">Moyenne générale</th>
                  <th className="py-1">Rang</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => {
                  const a = averages[s.id];
                  return (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="py-1 pr-4">{s.last_name} {s.first_name}</td>
                      <td className="py-1 pr-4">{a?.subject != null ? a.subject.toFixed(2) : "—"}</td>
                      <td className="py-1 pr-4">{a?.general != null ? a.general.toFixed(2) : "—"}</td>
                      <td className="py-1">{a?.rank ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {activeAssessment && (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Saisie : {activeAssessment.name}</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {students.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3">
                <span>{s.last_name} {s.first_name}</span>
                <span className="flex items-center gap-2">
                  <input
                    type="number"
                    min="0"
                    max={activeAssessment.max_score}
                    aria-label={`Note de ${s.last_name}`}
                    value={scores[s.id]?.score ?? ""}
                    disabled={!scoresLoaded || scores[s.id]?.absent}
                    onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: e.target.value, absent: prev[s.id]?.absent ?? false } }))}
                    className="w-24 rounded border border-slate-300 px-2 py-1"
                  />
                  <label className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      disabled={!scoresLoaded}
                      checked={scores[s.id]?.absent ?? false}
                      onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: "", absent: e.target.checked } }))}
                    />
                    Absent
                  </label>
                </span>
              </li>
            ))}
          </ul>
          <button type="button" onClick={saveScores} disabled={busy || !scoresLoaded} className="mt-4 rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50">
            Enregistrer les notes
          </button>
        </section>
      )}
    </div>
  );
}

export default function TeacherGradesPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-400">Chargement...</p>}>
      <TeacherGradesPageContent />
    </Suspense>
  );
}
