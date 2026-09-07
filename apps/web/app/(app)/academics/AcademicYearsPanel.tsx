"use client";

import { ResourceCrudPanel, type FieldSpec, type FieldValues } from "@/components/crud/ResourceCrudPanel";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { academicTerms, academicYears, type AcademicTerm, type AcademicYear } from "@/lib/academics/client";
import { useAsyncData } from "@/lib/api/useAsyncData";

const YEAR_FIELDS: FieldSpec<AcademicYear>[] = [
  { key: "name", label: "Nom", type: "text", required: true },
  { key: "start_date", label: "Début", type: "date", required: true },
  { key: "end_date", label: "Fin", type: "date", required: true },
  { key: "is_current", label: "Année en cours", type: "checkbox" },
];

const TERM_FIELDS: FieldSpec<AcademicTerm>[] = [
  { key: "name", label: "Nom", type: "text", required: true },
  { key: "start_date", label: "Début", type: "date", required: true },
  { key: "end_date", label: "Fin", type: "date", required: true },
  { key: "order_index", label: "Ordre", type: "number" },
];

function YearTermsPanel({ year, canManage }: { year: AcademicYear; canManage: boolean }) {
  const list = useAsyncData(() => academicTerms.list(year.id), [year.id]);

  if (list.isLoading) return <p className="text-sm text-slate-400">Chargement des périodes...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;

  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<AcademicTerm>
        title={`Périodes — ${year.name}`}
        items={list.data}
        fields={TERM_FIELDS}
        canManage={canManage}
        onCreate={(values: FieldValues) =>
          academicTerms.create({
            academic_year_id: year.id,
            name: values.name as string,
            start_date: values.start_date as string,
            end_date: values.end_date as string,
            order_index: values.order_index === "" ? undefined : Number(values.order_index),
          })
        }
        onUpdate={(id, values) =>
          academicTerms.update(id, {
            name: values.name as string,
            start_date: values.start_date as string,
            end_date: values.end_date as string,
            order_index: values.order_index === "" ? undefined : Number(values.order_index),
          })
        }
        onItemCreated={() => list.retry()}
        onItemUpdated={() => list.retry()}
      />
    </div>
  );
}

export function AcademicYearsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => academicYears.list(schoolId), [schoolId]);

  if (list.isLoading) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;

  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<AcademicYear>
        title="Années scolaires"
        items={list.data}
        fields={YEAR_FIELDS}
        canManage={canManage}
        onCreate={(values) =>
          academicYears.create({
            school_id: schoolId,
            name: values.name as string,
            start_date: values.start_date as string,
            end_date: values.end_date as string,
            is_current: Boolean(values.is_current),
          })
        }
        onUpdate={(id, values) =>
          academicYears.update(id, {
            name: values.name as string,
            start_date: values.start_date as string,
            end_date: values.end_date as string,
            is_current: Boolean(values.is_current),
          })
        }
        onItemCreated={() => list.retry()}
        onItemUpdated={() => list.retry()}
        renderRowExtra={(year) => <YearTermsPanel year={year} canManage={canManage} />}
      />
    </div>
  );
}
