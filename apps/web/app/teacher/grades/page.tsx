"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { academicTerms } from "@/lib/academics/client";
import {
  assessmentTypes,
  assessments as assessmentsApi,
  classPerformance,
  results,
  studentAverages,
  type AssessmentType,
} from "@/lib/grades/client";
import { describeTeacherError, teacherApi, type TeacherAssessment, type TeacherClass, type TeacherStudent } from "@/lib/teacher/client";

// Notes & évaluations du portail. Les matières proposées sont uniquement celles de l'enseignant
// (TeacherAssignment). La création d'évaluation et la saisie passent par les endpoints existants,
// qui refusent déjà toute matière non affectée (contrôle backend, vérifié dans les tests).
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
  const [activeAssessment, setActiveAssessment] = useState<TeacherAssessment | null>(null);
  const [scores, setScores] = useState<Record<string, { score: string; absent: boolean }>>({});
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
    if (!classSubjectId || !termId || !typeId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await assessmentsApi.create({
        class_subject_id: classSubjectId,
        academic_term_id: termId,
        assessment_type_id: typeId,
        name: form.name,
        max_score: Number(form.max_score),
        assessment_date: form.assessment_date,
      });
      setMessage("Évaluation créée.");
      if (selectedClass) setAssessments(await teacherApi.assessments(selectedClass.id));
      setForm((f) => ({ ...f, name: "" }));
    } catch (err) {
      setError(describeTeacherError(err));
    } finally {
      setBusy(false);
    }
  }

  async function openAssessment(assessment: TeacherAssessment) {
    setActiveAssessment(assessment);
    setError(null);
    setMessage(null);
    try {
      const list = await results.list(assessment.id);
      setScores(Object.fromEntries(list.map((r) => [r.student_id, { score: r.score == null ? "" : String(r.score), absent: r.is_absent }])));
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  async function saveScores() {
    if (!activeAssessment) return;
    setBusy(true);
    setError(null);
    try {
      await results.submit(
        activeAssessment.id,
        students.map((s) => {
          const entry = scores[s.id];
          return { student_id: s.id, score: entry?.absent || !entry?.score ? null : Number(entry.score), is_absent: entry?.absent ?? false };
        }),
      );
      setMessage("Notes enregistrées.");
    } catch (err) {
      setError(describeTeacherError(err));
    } finally {
      setBusy(false);
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
        {assessments.length === 0 ? (
          <p className="text-sm text-slate-400">Aucune évaluation pour cette classe.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {assessments.map((a) => (
              <li key={a.id}>
                <button type="button" onClick={() => openAssessment(a)} className="text-slate-900 underline">
                  {a.name} — {a.subject_name} ({a.assessment_date}, /{a.max_score})
                </button>
              </li>
            ))}
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
                    disabled={scores[s.id]?.absent}
                    onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: e.target.value, absent: prev[s.id]?.absent ?? false } }))}
                    className="w-24 rounded border border-slate-300 px-2 py-1"
                  />
                  <label className="flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={scores[s.id]?.absent ?? false}
                      onChange={(e) => setScores((prev) => ({ ...prev, [s.id]: { score: "", absent: e.target.checked } }))}
                    />
                    Absent
                  </label>
                </span>
              </li>
            ))}
          </ul>
          <button type="button" onClick={saveScores} disabled={busy} className="mt-4 rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50">
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
