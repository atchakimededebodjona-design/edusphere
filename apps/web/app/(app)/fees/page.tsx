"use client";

import { useId, useState } from "react";
import { ResourceCrudPanel, type FieldSpec } from "@/components/crud/ResourceCrudPanel";
import { Button } from "@/components/ui/Button";
import { DataTable, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { SelectField, TextField } from "@/components/ui/Field";
import { Badge, Card, EmptyState, PageHeader, SectionTitle } from "@/components/ui/Surface";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { academicYears, educationLevels, schoolClasses, type AcademicYear, type EducationLevel, type SchoolClass } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import {
  feeCategories,
  feeSchedules,
  type FeeCategory,
  type FeeSchedule,
  type FeeScopeType,
} from "@/lib/fees/client";
import { formatDateFR } from "@/lib/format/date";

const CATEGORY_FIELDS: FieldSpec<FeeCategory>[] = [{ key: "name", label: "Nom", type: "text", required: true }];

function CategoriesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => feeCategories.list(schoolId), [schoolId]);
  if (list.isLoading) return <TableSkeleton rows={3} />;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<FeeCategory>
        title="Catégories de frais"
        items={list.data}
        fields={CATEGORY_FIELDS}
        canManage={canManage}
        onCreate={(values) => feeCategories.create({ school_id: schoolId, name: values.name as string })}
        onUpdate={() => {
          throw new Error("La modification d'une catégorie n'est pas prise en charge.");
        }}
        onItemCreated={() => list.retry()}
        onItemUpdated={() => {}}
      />
    </div>
  );
}

type SchedulesData = {
  schedules: FeeSchedule[];
  categories: FeeCategory[];
  years: AcademicYear[];
  levels: EducationLevel[];
  classes: SchoolClass[];
};

const checkboxClass = "h-5 w-5 rounded border-slate-400 accent-primary-600";

function SchedulesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData<SchedulesData>(async () => {
    const [schedules, categories, years, levels, classes] = await Promise.all([
      feeSchedules.list(schoolId),
      feeCategories.list(schoolId),
      academicYears.list(schoolId),
      educationLevels.list(schoolId),
      schoolClasses.list(schoolId),
    ]);
    return { schedules, categories, years, levels, classes };
  }, [schoolId]);
  const [error, setError] = useState<string | null>(null);
  const [generateResult, setGenerateResult] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState<string | null>(null);

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

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await feeSchedules.create({
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
      setForm((prev) => ({ ...prev, name: "", amount: "", due_date: "" }));
      list.retry();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }

  async function handleGenerate(scheduleId: string) {
    setGenerating(scheduleId);
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
    } finally {
      setGenerating(null);
    }
  }

  if (list.isLoading) return <TableSkeleton />;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  const { schedules, categories, years, levels, classes } = list.data;

  const categoryName = (id: string) => categories.find((c) => c.id === id)?.name ?? "—";
  const yearName = (id: string) => years.find((y) => y.id === id)?.name ?? "—";
  const scopeLabel = (s: FeeSchedule) =>
    s.scope_type === "CLASS"
      ? `Classe : ${classes.find((c) => c.id === s.scope_class_id)?.name ?? "—"}`
      : s.scope_type === "LEVEL"
        ? `Niveau : ${levels.find((l) => l.id === s.scope_education_level_id)?.name ?? "—"}`
        : "Toute l'école";
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const columns: Column<FeeSchedule>[] = [
    {
      key: "name",
      header: "Nom",
      mobile: "title",
      cell: (s) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-900">{s.name}</span>
          {s.is_optional && <Badge tone="info">Facultatif</Badge>}
        </span>
      ),
    },
    { key: "category", header: "Catégorie", cell: (s) => categoryName(s.fee_category_id) },
    { key: "year", header: "Année", cell: (s) => yearName(s.academic_year_id) },
    { key: "scope", header: "Portée", cell: scopeLabel },
    { key: "due", header: "Échéance", cell: (s) => (s.due_date ? formatDateFR(s.due_date) : "—") },
    {
      key: "amount",
      header: "Montant",
      align: "right",
      cell: (s) => <span className="font-semibold text-slate-900">{formatApiAmount(s.amount, s.currency)}</span>,
    },
    ...(canManage
      ? [
          {
            key: "generate",
            header: <span className="sr-only">Actions</span>,
            align: "right" as const,
            mobile: "full" as const,
            cell: (s: FeeSchedule) => (
              <div className="flex flex-col gap-1 sm:items-end">
                <Button
                  variant="quiet"
                  size="sm"
                  className="max-sm:-ml-3 max-sm:self-start"
                  disabled={generating === s.id}
                  onClick={() => void handleGenerate(s.id)}
                >
                  {generating === s.id ? "Génération..." : "Générer les frais élèves"}
                </Button>
                {generateResult[s.id] && (
                  <p role="status" className="text-xs text-slate-700">
                    {generateResult[s.id]}
                  </p>
                )}
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-4">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <SectionTitle title="Barèmes" />
      <DataTable
        caption="Barèmes"
        columns={columns}
        rows={schedules}
        rowKey={(s) => s.id}
        empty={
          <EmptyState
            icon="wallet"
            title="Aucun barème."
            description={canManage ? "Créez une catégorie, puis un barème avec le formulaire ci-dessous." : undefined}
          />
        }
      />

      {canManage && (
        <form onSubmit={handleCreate}>
          <Card className="flex flex-col gap-4">
            <div>
              <p className="text-base font-bold text-slate-900">Nouveau barème</p>
              <p className="text-sm text-slate-600">
                Une fois créé, « Générer les frais élèves » ajoute ce montant à chaque élève concerné.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <SelectField label="Catégorie" value={form.fee_category_id} onChange={set("fee_category_id")} required>
                <option value="">—</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Année académique" value={form.academic_year_id} onChange={set("academic_year_id")} required>
                <option value="">—</option>
                {years.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
              </SelectField>
              <TextField label="Nom" value={form.name} onChange={set("name")} required placeholder="Ex. Frais de scolarité" />
              <TextField label="Montant" type="number" inputMode="decimal" min="0.01" step="0.01" value={form.amount} onChange={set("amount")} required />
              <SelectField label="Portée" value={form.scope_type} onChange={set("scope_type")}>
                <option value="SCHOOL">Toute l&apos;école</option>
                <option value="CLASS">Une classe</option>
                <option value="LEVEL">Un niveau</option>
              </SelectField>
              {form.scope_type === "CLASS" && (
                <SelectField label="Classe" value={form.scope_class_id} onChange={set("scope_class_id")} required>
                  <option value="">—</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </SelectField>
              )}
              {form.scope_type === "LEVEL" && (
                <SelectField label="Niveau" value={form.scope_education_level_id} onChange={set("scope_education_level_id")} required>
                  <option value="">—</option>
                  {levels.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </SelectField>
              )}
              <TextField label="Échéance" type="date" value={form.due_date} onChange={set("due_date")} hint="Facultatif" />
              <label className="flex min-h-11 items-center gap-2 self-center text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={form.is_optional}
                  onChange={(e) => setForm((prev) => ({ ...prev, is_optional: e.target.checked }))}
                  className={checkboxClass}
                />
                Optionnel
              </label>
            </div>
            {error && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {error}
              </p>
            )}
            <Button type="submit" icon="plus" className="self-start">
              Ajouter
            </Button>
          </Card>
        </form>
      )}
    </div>
  );
}

const TABS = [
  { key: "categories", label: "Catégories" },
  { key: "schedules", label: "Barèmes" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export default function FeesPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("fees.manage");
  const [tab, setTab] = useState<Tab>("categories");
  const tabsId = useId();

  if (!currentSchoolId) return <TableSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Frais scolaires" description="Catégories de frais et barèmes par année, puis génération des frais de chaque élève." />
      <div>
        <Tabs id={tabsId} label="Frais scolaires" tabs={[...TABS]} value={tab} onChange={setTab} />
        <TabPanel id={tabsId} active={tab}>
          {tab === "categories" && <CategoriesPanel schoolId={currentSchoolId} canManage={canManage} />}
          {tab === "schedules" && <SchedulesPanel schoolId={currentSchoolId} canManage={canManage} />}
        </TabPanel>
      </div>
    </div>
  );
}
