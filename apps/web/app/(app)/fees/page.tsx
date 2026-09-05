"use client";

import { useEffect, useState } from "react";
import { ResourceCrudPanel, type FieldSpec } from "@/components/crud/ResourceCrudPanel";
import { ApiError } from "@/lib/api/client";
import { academicYears, educationLevels, schoolClasses, type AcademicYear, type EducationLevel, type SchoolClass } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import {
  feeCategories,
  feeSchedules,
  type FeeCategory,
  type FeeSchedule,
  type FeeScopeType,
} from "@/lib/fees/client";

const CATEGORY_FIELDS: FieldSpec<FeeCategory>[] = [{ key: "name", label: "Nom", type: "text", required: true }];

function CategoriesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [items, setItems] = useState<FeeCategory[] | null>(null);
  useEffect(() => {
    void feeCategories.list(schoolId).then(setItems);
  }, [schoolId]);
  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;
  return (
    <ResourceCrudPanel<FeeCategory>
      title="Catégories de frais"
      items={items}
      fields={CATEGORY_FIELDS}
      canManage={canManage}
      onCreate={(values) => feeCategories.create({ school_id: schoolId, name: values.name as string })}
      onUpdate={() => {
        throw new Error("La modification d'une catégorie n'est pas prise en charge.");
      }}
      onItemCreated={(item) => setItems((prev) => [...(prev ?? []), item])}
      onItemUpdated={() => {}}
    />
  );
}

function SchedulesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [schedules, setSchedules] = useState<FeeSchedule[] | null>(null);
  const [categories, setCategories] = useState<FeeCategory[] | null>(null);
  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [levels, setLevels] = useState<EducationLevel[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generateResult, setGenerateResult] = useState<Record<string, string>>({});

  const [form, setForm] = useState({
    fee_category_id: "",
    academic_year_id: "",
    name: "",
    amount: "",
    scope_type: "SCHOOL" as FeeScopeType,
    scope_class_id: "",
    scope_education_level_id: "",
    is_optional: false,
    due_date: "",
  });

  useEffect(() => {
    void Promise.all([
      feeSchedules.list(schoolId),
      feeCategories.list(schoolId),
      academicYears.list(schoolId),
      educationLevels.list(schoolId),
      schoolClasses.list(schoolId),
    ]).then(([s, c, y, l, cl]) => {
      setSchedules(s);
      setCategories(c);
      setYears(y);
      setLevels(l);
      setClasses(cl);
    });
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const created = await feeSchedules.create({
        school_id: schoolId,
        fee_category_id: form.fee_category_id,
        academic_year_id: form.academic_year_id,
        name: form.name,
        amount: form.amount,
        scope_type: form.scope_type,
        scope_class_id: form.scope_type === "CLASS" ? form.scope_class_id : null,
        scope_education_level_id: form.scope_type === "LEVEL" ? form.scope_education_level_id : null,
        is_optional: form.is_optional,
        due_date: form.due_date || null,
      });
      setSchedules((prev) => [...(prev ?? []), created]);
      setForm((prev) => ({ ...prev, name: "", amount: "", due_date: "" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }

  async function handleGenerate(scheduleId: string) {
    try {
      const result = await feeSchedules.generate(scheduleId);
      setGenerateResult((prev) => ({
        ...prev,
        [scheduleId]: `${result.created_count} élève(s) affecté(s), ${result.skipped_existing_count} déjà à jour.`,
      }));
    } catch (err) {
      setGenerateResult((prev) => ({
        ...prev,
        [scheduleId]: err instanceof ApiError ? err.message : "Échec de la génération.",
      }));
    }
  }

  if (schedules === null || categories === null || years === null || levels === null || classes === null) {
    return <p className="text-sm text-slate-400">Chargement...</p>;
  }

  const categoryName = (id: string) => categories.find((c) => c.id === id)?.name ?? "—";
  const yearName = (id: string) => years.find((y) => y.id === id)?.name ?? "—";

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Catégorie</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Année</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Portée</th>
              <th className="px-3 py-2 text-right font-medium text-slate-600">Montant</th>
              {canManage && <th className="px-3 py-2" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {schedules.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2">{s.name}</td>
                <td className="px-3 py-2">{categoryName(s.fee_category_id)}</td>
                <td className="px-3 py-2">{yearName(s.academic_year_id)}</td>
                <td className="px-3 py-2">{s.scope_type}</td>
                <td className="px-3 py-2 text-right">
                  {s.amount} {s.currency}
                </td>
                {canManage && (
                  <td className="px-3 py-2 text-right">
                    <button type="button" onClick={() => void handleGenerate(s.id)} className="text-xs text-slate-700 underline">
                      Générer les frais élèves
                    </button>
                    {generateResult[s.id] && <p className="mt-1 text-xs text-slate-500">{generateResult[s.id]}</p>}
                  </td>
                )}
              </tr>
            ))}
            {schedules.length === 0 && (
              <tr>
                <td colSpan={canManage ? 6 : 5} className="px-3 py-4 text-center text-slate-400">
                  Aucun barème.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Catégorie
            <select
              value={form.fee_category_id}
              onChange={(e) => setForm((prev) => ({ ...prev, fee_category_id: e.target.value }))}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Année académique
            <select
              value={form.academic_year_id}
              onChange={(e) => setForm((prev) => ({ ...prev, academic_year_id: e.target.value }))}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {years.map((y) => (
                <option key={y.id} value={y.id}>
                  {y.name}
                </option>
              ))}
            </select>
          </label>
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
            Montant
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm((prev) => ({ ...prev, amount: e.target.value }))}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Portée
            <select
              value={form.scope_type}
              onChange={(e) => setForm((prev) => ({ ...prev, scope_type: e.target.value as FeeScopeType }))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="SCHOOL">Toute l&apos;école</option>
              <option value="CLASS">Une classe</option>
              <option value="LEVEL">Un niveau</option>
            </select>
          </label>
          {form.scope_type === "CLASS" && (
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Classe
              <select
                value={form.scope_class_id}
                onChange={(e) => setForm((prev) => ({ ...prev, scope_class_id: e.target.value }))}
                required
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="">—</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.scope_type === "LEVEL" && (
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Niveau
              <select
                value={form.scope_education_level_id}
                onChange={(e) => setForm((prev) => ({ ...prev, scope_education_level_id: e.target.value }))}
                required
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="">—</option>
                {levels.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Échéance
            <input
              type="date"
              value={form.due_date}
              onChange={(e) => setForm((prev) => ({ ...prev, due_date: e.target.value }))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={form.is_optional}
              onChange={(e) => setForm((prev) => ({ ...prev, is_optional: e.target.checked }))}
            />
            Optionnel
          </label>
          <button type="submit" className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">
            Ajouter
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

const TABS = ["Catégories", "Barèmes"] as const;
type Tab = (typeof TABS)[number];

export default function FeesPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("fees.manage");
  const [tab, setTab] = useState<Tab>("Catégories");

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Frais scolaires</h1>

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

      {tab === "Catégories" && <CategoriesPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Barèmes" && <SchedulesPanel schoolId={currentSchoolId} canManage={canManage} />}
    </div>
  );
}
