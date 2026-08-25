"use client";

import { useEffect, useMemo, useState } from "react";
import { academicTerms, classSubjects, schoolClasses, subjects as subjectsClient, type AcademicTerm, type ClassSubject, type SchoolClass, type Subject } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import {
  assessmentTypes,
  assessments as assessmentsClient,
  subjectAverages,
  studentAverages,
  type Assessment,
  type AssessmentType,
  type StudentSubjectAverage,
} from "@/lib/grades/client";
import { students as studentsClient, type Student } from "@/lib/students/client";
import { AssessmentGradeEntry } from "@/app/(app)/grades/AssessmentGradeEntry";

function AppreciationCell({
  average,
  canManage,
  onSaved,
}: {
  average: StudentSubjectAverage;
  canManage: boolean;
  onSaved: (updated: StudentSubjectAverage) => void;
}) {
  const [value, setValue] = useState(average.appreciation ?? "");
  const [saving, setSaving] = useState(false);

  async function handleBlur() {
    if (value === (average.appreciation ?? "") || !canManage) return;
    setSaving(true);
    try {
      const updated = await subjectAverages.updateAppreciation(average.id, value);
      onSaved(updated);
    } finally {
      setSaving(false);
    }
  }

  return (
    <input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleBlur}
      disabled={!canManage || saving}
      placeholder="Appréciation"
      className="w-full rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
    />
  );
}

export function GradeBookPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [types, setTypes] = useState<AssessmentType[] | null>(null);

  const [selectedClassId, setSelectedClassId] = useState("");
  const [classSubjectOptions, setClassSubjectOptions] = useState<ClassSubject[] | null>(null);
  const [selectedClassSubjectId, setSelectedClassSubjectId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);

  const [assessmentList, setAssessmentList] = useState<Assessment[] | null>(null);
  const [expandedAssessmentId, setExpandedAssessmentId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", assessment_type_id: "", max_score: "20", weight: "1", assessment_date: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [averages, setAverages] = useState<Record<string, StudentSubjectAverage | undefined> | null>(null);

  useEffect(() => {
    void schoolClasses.list(schoolId).then(setClasses);
    void subjectsClient.list(schoolId).then(setSubjects);
    void assessmentTypes.list(schoolId).then(setTypes);
  }, [schoolId]);

  useEffect(() => {
    setSelectedClassSubjectId("");
    setSelectedTermId("");
    setClassSubjectOptions(null);
    setTerms(null);
    setRoster(null);
    if (!selectedClassId) return;
    void classSubjects.list(selectedClassId).then(setClassSubjectOptions);
    void studentsClient.list(schoolId, { classId: selectedClassId }).then(setRoster);
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) void academicTerms.list(schoolClass.academic_year_id).then(setTerms);
  }, [selectedClassId, schoolId, classes]);

  useEffect(() => {
    setAssessmentList(null);
    setExpandedAssessmentId(null);
    if (!selectedClassSubjectId || !selectedTermId) return;
    void assessmentsClient.list(selectedClassSubjectId, selectedTermId).then(setAssessmentList);
  }, [selectedClassSubjectId, selectedTermId]);

  useEffect(() => {
    setAverages(null);
    if (!selectedClassSubjectId || !selectedTermId || !roster) return;
    void Promise.all(roster.map((s) => studentAverages.get(s.id, selectedTermId))).then((results) => {
      const map: Record<string, StudentSubjectAverage | undefined> = {};
      roster.forEach((s, i) => {
        map[s.id] = results[i].subject_averages.find((a) => a.class_subject_id === selectedClassSubjectId);
      });
      setAverages(map);
    });
  }, [selectedClassSubjectId, selectedTermId, roster]);

  const sortedRoster = useMemo(() => (roster ?? []).slice().sort((a, b) => a.last_name.localeCompare(b.last_name)), [roster]);

  async function handleCreateAssessment(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await assessmentsClient.create({
        class_subject_id: selectedClassSubjectId,
        academic_term_id: selectedTermId,
        assessment_type_id: form.assessment_type_id,
        name: form.name,
        max_score: Number(form.max_score),
        weight: Number(form.weight),
        assessment_date: form.assessment_date,
      });
      setAssessmentList((prev) => [...(prev ?? []), created]);
      setForm({ name: "", assessment_type_id: "", max_score: "20", weight: "1", assessment_date: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (classes === null || subjects === null || types === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Classe
          <select value={selectedClassId} onChange={(e) => setSelectedClassId(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">
            <option value="">—</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Matière
          <select
            value={selectedClassSubjectId}
            onChange={(e) => setSelectedClassSubjectId(e.target.value)}
            disabled={!classSubjectOptions}
            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
          >
            <option value="">—</option>
            {classSubjectOptions?.map((cs) => (
              <option key={cs.id} value={cs.id}>
                {subjects.find((s) => s.id === cs.subject_id)?.name ?? cs.subject_id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Période
          <select
            value={selectedTermId}
            onChange={(e) => setSelectedTermId(e.target.value)}
            disabled={!terms}
            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
          >
            <option value="">—</option>
            {terms?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selectedClassSubjectId && selectedTermId && (
        <>
          <div className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Évaluations</h2>
            {assessmentList === null ? (
              <p className="text-sm text-slate-400">Chargement...</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {assessmentList.map((a) => (
                  <li key={a.id} className="rounded border border-slate-200">
                    <button
                      type="button"
                      onClick={() => setExpandedAssessmentId(expandedAssessmentId === a.id ? null : a.id)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
                    >
                      <span>
                        {expandedAssessmentId === a.id ? "▾" : "▸"} {a.name} — {a.assessment_date}
                      </span>
                      <span className="text-xs text-slate-500">/{a.max_score}</span>
                    </button>
                    {expandedAssessmentId === a.id && roster && (
                      <div className="border-t border-slate-200 p-3">
                        <AssessmentGradeEntry assessment={a} roster={roster} canManage={canManage} />
                      </div>
                    )}
                  </li>
                ))}
                {assessmentList.length === 0 && <li className="text-sm text-slate-400">Aucune évaluation pour cette sélection.</li>}
              </ul>
            )}

            {canManage && (
              <form onSubmit={handleCreateAssessment} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Nom
                  <input
                    value={form.name}
                    onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                    required
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Type
                  <select
                    value={form.assessment_type_id}
                    onChange={(e) => setForm((prev) => ({ ...prev, assessment_type_id: e.target.value }))}
                    required
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                  >
                    <option value="">—</option>
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Note max
                  <input
                    type="number"
                    value={form.max_score}
                    onChange={(e) => setForm((prev) => ({ ...prev, max_score: e.target.value }))}
                    className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Coefficient
                  <input
                    type="number"
                    step="0.5"
                    value={form.weight}
                    onChange={(e) => setForm((prev) => ({ ...prev, weight: e.target.value }))}
                    className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-slate-600">
                  Date
                  <input
                    type="date"
                    value={form.assessment_date}
                    onChange={(e) => setForm((prev) => ({ ...prev, assessment_date: e.target.value }))}
                    required
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </label>
                <button type="submit" disabled={creating} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                  {creating ? "Ajout..." : "Ajouter"}
                </button>
              </form>
            )}
            {error && <p className="text-sm text-red-700">{error}</p>}
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Moyennes &amp; appréciations</h2>
            {averages === null ? (
              <p className="text-sm text-slate-400">Chargement...</p>
            ) : (
              <div className="overflow-x-auto rounded border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Élève</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Moyenne</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Rang</th>
                      <th className="px-3 py-2 text-left font-medium text-slate-600">Appréciation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {sortedRoster.map((student) => {
                      const average = averages[student.id];
                      return (
                        <tr key={student.id}>
                          <td className="px-3 py-2">
                            {student.last_name} {student.first_name}
                          </td>
                          <td className="px-3 py-2">{average?.average ?? "—"}</td>
                          <td className="px-3 py-2">{average?.rank ?? "—"}</td>
                          <td className="px-3 py-2">
                            {average ? (
                              <AppreciationCell
                                average={average}
                                canManage={canManage}
                                onSaved={(updated) => setAverages((prev) => ({ ...prev, [student.id]: updated }))}
                              />
                            ) : (
                              <span className="text-xs text-slate-400">Pas encore de notes</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
