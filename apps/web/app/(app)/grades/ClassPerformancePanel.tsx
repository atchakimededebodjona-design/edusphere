"use client";

import { useEffect, useMemo, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import { classPerformance, type ClassPerformance } from "@/lib/grades/client";
import { students as studentsClient, type Student } from "@/lib/students/client";

export function ClassPerformancePanel({ schoolId }: { schoolId: string }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);
  const [performance, setPerformance] = useState<ClassPerformance | null>(null);

  useEffect(() => {
    void schoolClasses.list(schoolId).then(setClasses);
  }, [schoolId]);

  useEffect(() => {
    setSelectedTermId("");
    setTerms(null);
    setRoster(null);
    setPerformance(null);
    if (!selectedClassId) return;
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) void academicTerms.list(schoolClass.academic_year_id).then(setTerms);
    void studentsClient.list(schoolId, { classId: selectedClassId }).then(setRoster);
  }, [selectedClassId, classes, schoolId]);

  useEffect(() => {
    setPerformance(null);
    if (!selectedClassId || !selectedTermId) return;
    void classPerformance.get(selectedClassId, selectedTermId).then(setPerformance);
  }, [selectedClassId, selectedTermId]);

  const rows = useMemo(() => {
    if (!performance || !roster) return [];
    return performance.students
      .map((entry) => ({ entry, student: roster.find((s) => s.id === entry.student_id) }))
      .sort((a, b) => (a.entry.rank ?? Infinity) - (b.entry.rank ?? Infinity));
  }, [performance, roster]);

  if (classes === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
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

      {selectedClassId && selectedTermId && (
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Rang</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Élève</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Moyenne</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {performance === null ? (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-slate-400">
                    Chargement...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-slate-400">
                    Aucune moyenne disponible pour cette période.
                  </td>
                </tr>
              ) : (
                rows.map(({ entry, student }) => (
                  <tr key={entry.student_id}>
                    <td className="px-3 py-2">{entry.rank ?? "—"}</td>
                    <td className="px-3 py-2">
                      {student ? `${student.last_name} ${student.first_name}` : entry.student_id}
                    </td>
                    <td className="px-3 py-2">{entry.average ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
