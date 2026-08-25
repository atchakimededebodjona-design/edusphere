"use client";

import { useEffect, useState } from "react";
import { ResourceCrudPanel, type FieldSpec, type FieldValues } from "@/components/crud/ResourceCrudPanel";
import { academicTerms, academicYears, type AcademicTerm, type AcademicYear } from "@/lib/academics/client";

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
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);

  useEffect(() => {
    void academicTerms.list(year.id).then(setTerms);
  }, [year.id]);

  if (terms === null) return <p className="text-sm text-slate-400">Chargement des périodes...</p>;

  return (
    <ResourceCrudPanel<AcademicTerm>
      title={`Périodes — ${year.name}`}
      items={terms}
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
      onItemCreated={(item) => setTerms((prev) => [...(prev ?? []), item])}
      onItemUpdated={(item) => setTerms((prev) => (prev ?? []).map((t) => (t.id === item.id ? item : t)))}
    />
  );
}

export function AcademicYearsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [years, setYears] = useState<AcademicYear[] | null>(null);

  useEffect(() => {
    void academicYears.list(schoolId).then(setYears);
  }, [schoolId]);

  if (years === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <ResourceCrudPanel<AcademicYear>
      title="Années scolaires"
      items={years}
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
      onItemCreated={(item) => setYears((prev) => [...(prev ?? []), item])}
      onItemUpdated={(item) => setYears((prev) => (prev ?? []).map((y) => (y.id === item.id ? item : y)))}
      renderRowExtra={(year) => <YearTermsPanel year={year} canManage={canManage} />}
    />
  );
}
