"use client";

import { useEffect, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import { attendanceStats, type AttendanceClassStatistics } from "@/lib/attendance/client";
import { students as studentsClient, type Student } from "@/lib/students/client";

export function AttendanceStatsPanel({ schoolId }: { schoolId: string }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);
  const [statistics, setStatistics] = useState<AttendanceClassStatistics | null>(null);

  useEffect(() => {
    void schoolClasses.list(schoolId).then(setClasses);
  }, [schoolId]);

  useEffect(() => {
    setSelectedTermId("");
    setTerms(null);
    setRoster(null);
    if (!selectedClassId) return;
    void studentsClient.list(schoolId, { classId: selectedClassId }).then(setRoster);
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) void academicTerms.list(schoolClass.academic_year_id).then(setTerms);
  }, [selectedClassId, schoolId, classes]);

  useEffect(() => {
    setStatistics(null);
    if (!selectedClassId || !selectedTermId) return;
    void attendanceStats.classStatistics(selectedClassId, selectedTermId).then(setStatistics);
  }, [selectedClassId, selectedTermId]);

  if (classes === null) return <p className="text-sm text-slate-400">Chargement...</p>;

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
        statistics === null || roster === null ? (
          <p className="text-sm text-slate-400">Chargement...</p>
        ) : (
          <div className="overflow-x-auto rounded border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Élève</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Présents</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Absents</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Retards</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Absences justifiées</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Taux de présence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {roster
                  .slice()
                  .sort((a, b) => a.last_name.localeCompare(b.last_name))
                  .map((student) => {
                    const entry = statistics.students.find((s) => s.student_id === student.id);
                    return (
                      <tr key={student.id}>
                        <td className="px-3 py-2">
                          {student.last_name} {student.first_name}
                        </td>
                        <td className="px-3 py-2">{entry?.present_count ?? 0}</td>
                        <td className="px-3 py-2">{entry?.absent_count ?? 0}</td>
                        <td className="px-3 py-2">{entry?.late_count ?? 0}</td>
                        <td className="px-3 py-2">{entry?.justified_absence_count ?? 0}</td>
                        <td className="px-3 py-2">{entry?.attendance_rate != null ? `${entry.attendance_rate}%` : "—"}</td>
                      </tr>
                    );
                  })}
                {roster.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                      Aucun élève inscrit dans cette classe.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
