"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { results, type Assessment, type AssessmentResult } from "@/lib/grades/client";
import type { Student } from "@/lib/students/client";

type RowValue = { score: string; is_absent: boolean };

export function AssessmentGradeEntry({
  assessment,
  roster,
  canManage,
}: {
  assessment: Assessment;
  roster: Student[];
  canManage: boolean;
}) {
  const [existing, setExisting] = useState<AssessmentResult[] | null>(null);
  const [values, setValues] = useState<Record<string, RowValue>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void results.list(assessment.id).then((rows) => {
      setExisting(rows);
      const initial: Record<string, RowValue> = {};
      for (const student of roster) {
        const row = rows.find((r) => r.student_id === student.id);
        initial[student.id] = {
          score: row?.score != null ? String(row.score) : "",
          is_absent: row?.is_absent ?? false,
        };
      }
      setValues(initial);
    });
  }, [assessment.id, roster]);

  const sortedRoster = useMemo(
    () => [...roster].sort((a, b) => a.last_name.localeCompare(b.last_name)),
    [roster],
  );

  function updateValue(studentId: string, patch: Partial<RowValue>) {
    setValues((prev) => ({ ...prev, [studentId]: { ...prev[studentId], ...patch } }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const entries = roster.map((student) => {
        const value = values[student.id] ?? { score: "", is_absent: false };
        return {
          student_id: student.id,
          score: value.is_absent || value.score === "" ? null : Number(value.score),
          is_absent: value.is_absent,
        };
      });
      const saved = await results.submit(assessment.id, entries);
      setExisting(saved);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setSaving(false);
    }
  }

  if (existing === null) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-600">
        Note sur {assessment.max_score} — coefficient {assessment.weight}
      </p>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Élève</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Note</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Absent</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sortedRoster.map((student) => {
              const value = values[student.id] ?? { score: "", is_absent: false };
              return (
                <tr key={student.id}>
                  <td className="px-3 py-2">
                    {student.last_name} {student.first_name}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      max={assessment.max_score}
                      step="0.25"
                      value={value.score}
                      onChange={(e) => updateValue(student.id, { score: e.target.value })}
                      disabled={!canManage || value.is_absent}
                      className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 !w-24"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={value.is_absent}
                      onChange={(e) => updateValue(student.id, { is_absent: e.target.checked })}
                      disabled={!canManage}
                    />
                  </td>
                </tr>
              );
            })}
            {sortedRoster.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-slate-600">
                  Aucun élève inscrit dans cette classe.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canManage && sortedRoster.length > 0 && (
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
        >
          {saving ? "Enregistrement..." : "Enregistrer les notes"}
        </button>
      )}
      {saved && <p className="text-sm text-green-700">Notes enregistrées.</p>}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  );
}
