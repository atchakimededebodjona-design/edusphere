"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { assessmentTypes, type AssessmentType } from "@/lib/grades/client";
import { useAuth } from "@/lib/auth/useAuth";
import { GradeBookPanel } from "@/app/(app)/grades/GradeBookPanel";
import { ClassPerformancePanel } from "@/app/(app)/grades/ClassPerformancePanel";

function AssessmentTypesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [items, setItems] = useState<AssessmentType[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void assessmentTypes.list(schoolId).then(setItems);
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await assessmentTypes.create({ school_id: schoolId, name });
      setItems((prev) => [...(prev ?? []), created]);
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Types d&apos;évaluation</h2>
      <ul className="flex flex-col gap-1">
        {items.map((t) => (
          <li key={t.id} className="rounded border border-slate-200 px-3 py-1.5 text-sm">
            {t.name}
          </li>
        ))}
        {items.length === 0 && <li className="text-sm text-slate-400">Aucun type d&apos;évaluation.</li>}
      </ul>
      {canManage && (
        <form onSubmit={handleCreate} className="flex items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Nom
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
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
  );
}

const TABS = ["Types d'évaluation", "Cahier de notes", "Performance de classe"] as const;
type Tab = (typeof TABS)[number];

export default function GradesPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("grades.manage");
  const [tab, setTab] = useState<Tab>("Cahier de notes");

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

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
      {tab === "Performance de classe" && <ClassPerformancePanel schoolId={currentSchoolId} />}
    </div>
  );
}
