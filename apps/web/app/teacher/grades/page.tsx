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
import { TeacherFormSkeleton } from "@/components/teacher-shell/TeacherFormSkeleton";
import { ActionBar } from "@/components/ui/ActionBar";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField, controlClass } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Alert, Badge, Card, EmptyState, PageHeader } from "@/components/ui/Surface";
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
import { useReveal } from "@/components/ui/useReveal";
import { describeTeacherError, teacherApi, type TeacherAssessment, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Notes & évaluations du portail. Les matières proposées sont uniquement celles de l'enseignant
// (TeacherAssignment). La création d'évaluation et la saisie passent par les endpoints existants,
// qui refusent déjà toute matière non affectée (contrôle backend, vérifié dans les tests).
//
// Phase 32, lot 2 — utilisable sans connexion : création d'évaluation et saisie des notes passent
// par la boîte d'envoi (lib/offline/sync.ts::saveNow), comme l'appel (voir teacher/attendance).

//
// Refonte, phase 2 (2026-11-23) — présentation seulement : champs avec libellés, évaluations en cartes,
// saisie juste sous la liste, grands champs de note et bouton d'enregistrement collé en bas de l'écran.
// Même saisie, mêmes contrôles, mêmes envois.

function frenchDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return day && month && year ? `${day}/${month}/${year}` : isoDate;
}

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
  // Refonte, phase 2 : la saisie ouverte est amenée à l'écran (sur téléphone, elle est sous la liste).
  const [reveal, setReveal] = useState(0);
  const entryRef = useReveal<HTMLElement>(reveal);
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

  if (classes === null && !error) return <TeacherFormSkeleton />;
  if (classes && classes.length === 0) {
    return <EmptyState icon="layers" title="Aucune classe" description="Aucune classe ne vous est affectée." />;
  }

  const allAssessments: AssessmentView[] = [...localAssessments, ...assessments];
  const filledCount = students.filter((s) => scores[s.id]?.absent || (scores[s.id]?.score ?? "") !== "").length;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Notes & évaluations" description="Choisissez la classe et la matière, ouvrez une évaluation, puis saisissez les notes." />
      <Card>
        <div className="grid items-end gap-3 sm:grid-cols-3">
          <SelectField label="Classe" value={classId} onChange={(e) => setClassId(e.target.value)}>
            {(classes ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SelectField>
          <SelectField label="Matière" value={classSubjectId} onChange={(e) => setClassSubjectId(e.target.value)}>
            {(selectedClass?.subjects ?? []).map((s) => <option key={s.class_subject_id} value={s.class_subject_id}>{s.subject_name}</option>)}
          </SelectField>
          <SelectField label="Période" value={termId} onChange={(e) => setTermId(e.target.value)}>
            {terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </SelectField>
        </div>
      </Card>

      <OutboxFailures kind="grades" />
      {error && <Alert tone="danger">{error}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="grades-assessments" className="flex flex-col gap-2">
          <h2 id="grades-assessments" className="text-lg font-bold text-slate-900">Évaluations</h2>
          {allAssessments.length === 0 ? (
            <p className="text-sm text-slate-600">Aucune évaluation pour cette classe.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {allAssessments.map((a) => {
                const state = entryStateFor(a);
                const current = activeAssessment?.id === a.id;
                return (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => {
                        void openAssessment(a);
                        setReveal((n) => n + 1);
                      }}
                      aria-pressed={current}
                      className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 ${
                        current ? "border-primary-600 bg-primary-50" : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block font-semibold text-slate-900">{a.name}</span>
                        <span className="block text-xs text-slate-600">
                          {a.subject_name} · {frenchDate(a.assessment_date)} · sur {a.max_score}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {state === "pending" && <Badge tone="warning">en attente d&apos;envoi</Badge>}
                        {state === "failed" && <Badge tone="danger">refusée par le serveur</Badge>}
                        <Icon name="chevronRight" className="h-4 w-4 text-slate-500" />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section aria-labelledby="grades-create">
          <Card className="flex flex-col gap-3">
            <h2 id="grades-create" className="text-lg font-bold text-slate-900">Créer une évaluation</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Nom de l'évaluation"
                placeholder="Ex. : Devoir n°1"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <SelectField label="Type" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
                {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </SelectField>
              <TextField
                label="Note maximale"
                type="number"
                min="1"
                inputMode="decimal"
                value={form.max_score}
                onChange={(e) => setForm({ ...form, max_score: e.target.value })}
              />
              <TextField
                label="Date de l'évaluation"
                type="date"
                value={form.assessment_date}
                onChange={(e) => setForm({ ...form, assessment_date: e.target.value })}
              />
            </div>
            <Button
              onClick={createAssessment}
              disabled={busy || !form.name || !classSubjectId || !termId || !typeId}
              icon="listChecks"
              className="w-full sm:w-fit"
            >
              Créer
            </Button>
          </Card>
        </section>
      </div>

      {activeAssessment && (
        <section ref={entryRef} aria-labelledby="grades-entry" className="flex scroll-mt-20 flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="grades-entry" className="text-lg font-bold text-slate-900">Saisie : {activeAssessment.name}</h2>
            <p className="text-sm text-slate-600">
              {activeAssessment.subject_name} · notes sur {activeAssessment.max_score}
            </p>
          </div>
          {students.length === 0 ? (
            <p className="text-sm text-slate-600">Aucun élève dans cette classe.</p>
          ) : (
            <Card padded={false}>
              <ul className="divide-y divide-slate-100">
                {students.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                    <span className="min-w-0 font-medium text-slate-900">
                      {s.last_name} {s.first_name}
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      <input
                        type="number"
                        min="0"
                        max={activeAssessment.max_score}
                        step="any"
                        inputMode="decimal"
                        aria-label={`Note de ${s.last_name} ${s.first_name}`}
                        value={scores[s.id]?.score ?? ""}
                        disabled={!scoresLoaded || scores[s.id]?.absent}
                        onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: e.target.value, absent: prev[s.id]?.absent ?? false } }))}
                        className={`${controlClass} w-24 text-right text-base font-semibold tabular-nums`}
                      />
                      <label className="flex min-h-11 items-center gap-2 text-sm text-slate-800 sm:min-h-9">
                        <input
                          type="checkbox"
                          disabled={!scoresLoaded}
                          checked={scores[s.id]?.absent ?? false}
                          onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: "", absent: e.target.checked } }))}
                          className="h-5 w-5 rounded border-slate-400 accent-primary-600"
                        />
                        Absent
                      </label>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <ActionBar className="-mx-4 px-4 md:mx-0 md:rounded-xl md:border">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-700">
                {scoresLoaded ? `${filledCount} / ${students.length} élève${students.length > 1 ? "s" : ""} noté${filledCount > 1 ? "s" : ""} ou absent${filledCount > 1 ? "s" : ""}` : "Chargement des notes..."}
              </p>
              <Button onClick={saveScores} disabled={busy || !scoresLoaded} icon="checkSquare" className="w-full sm:w-auto">
                Enregistrer les notes
              </Button>
            </div>
          </ActionBar>
        </section>
      )}

      <section aria-labelledby="grades-averages" className="flex flex-col gap-2">
        <h2 id="grades-averages" className="text-lg font-bold text-slate-900">
          Moyennes — {terms.find((t) => t.id === termId)?.name ?? "période"}
        </h2>
        {students.length === 0 ? (
          <p className="text-sm text-slate-600">Aucun élève dans cette classe.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
                <tr>
                  <th scope="col" className="px-4 py-2">Élève</th>
                  <th scope="col" className="px-4 py-2 text-right">Moy. matière</th>
                  <th scope="col" className="px-4 py-2 text-right">Moy. générale</th>
                  <th scope="col" className="px-4 py-2 text-right">Rang</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {students.map((s) => {
                  const a = averages[s.id];
                  return (
                    <tr key={s.id}>
                      <td className="px-4 py-2 text-slate-900">{s.last_name} {s.first_name}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{a?.subject != null ? a.subject.toFixed(2) : "—"}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{a?.general != null ? a.general.toFixed(2) : "—"}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{a?.rank ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function TeacherGradesPage() {
  return (
    <Suspense fallback={<TeacherFormSkeleton />}>
      <TeacherGradesPageContent />
    </Suspense>
  );
}
