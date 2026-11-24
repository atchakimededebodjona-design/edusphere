"use client";

import { useState } from "react";
import { TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { assessmentTypes } from "@/lib/grades/client";
import { useAuth } from "@/lib/auth/useAuth";
import { GradeBookPanel } from "@/app/(app)/grades/GradeBookPanel";
import { ClassPerformancePanel } from "@/app/(app)/grades/ClassPerformancePanel";

function AssessmentTypesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => assessmentTypes.list(schoolId), [schoolId]);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await assessmentTypes.create({ school_id: schoolId, name });
      setName("");
      list.retry();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (list.isLoading) return <TableSkeleton rows={3} />;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  const items = list.data;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Types d&apos;évaluation</h2>
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ul className="flex flex-col gap-1">
        {items.map((t) => (
          <li key={t.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            {t.name}
          </li>
        ))}
        {items.length === 0 && <li className="text-sm text-slate-600">Aucun type d&apos;évaluation.</li>}
      </ul>
      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Nom
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            />
          </label>
          <button type="submit" disabled={creating} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
            {creating ? "Ajout..." : "Ajouter"}
          </button>
        </form>
      )}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  );
}

const TABS = ["Types d'évaluation", "Cahier de notes", "Performance de classe"] as const;
type Tab = (typeof TABS)[number];

export default function GradesPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("grades.manage");
  const canExport = permissions.includes("grades.read");
  const [tab, setTab] = useState<Tab>("Cahier de notes");

  if (!currentSchoolId) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Notes</h1>

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium ${
              tab === t ? "border-b-2 border-slate-900 text-slate-900" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Types d'évaluation" && <AssessmentTypesPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Cahier de notes" && <GradeBookPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Performance de classe" && <ClassPerformancePanel schoolId={currentSchoolId} canExport={canExport} />}
    </div>
  );
}
