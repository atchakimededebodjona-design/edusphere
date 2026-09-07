"use client";

import { useState } from "react";
import { ResourceCrudPanel, type FieldSpec } from "@/components/crud/ResourceCrudPanel";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { educationLevels, rooms, subjects, type EducationLevel, type Room, type Subject } from "@/lib/academics/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { AcademicYearsPanel } from "@/app/(app)/academics/AcademicYearsPanel";
import { ClassesPanel } from "@/app/(app)/academics/ClassesPanel";

const LEVEL_FIELDS: FieldSpec<EducationLevel>[] = [
  { key: "name", label: "Nom", type: "text", required: true },
  { key: "order_index", label: "Ordre", type: "number" },
];

const SUBJECT_FIELDS: FieldSpec<Subject>[] = [
  { key: "name", label: "Nom", type: "text", required: true },
  { key: "code", label: "Code", type: "text" },
];

const ROOM_FIELDS: FieldSpec<Room>[] = [
  { key: "name", label: "Nom", type: "text", required: true },
  { key: "capacity", label: "Capacité", type: "number" },
];

function EducationLevelsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => educationLevels.list(schoolId), [schoolId]);
  if (list.isLoading) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<EducationLevel>
      title="Niveaux"
      items={list.data}
      fields={LEVEL_FIELDS}
      canManage={canManage}
      onCreate={(values) =>
        educationLevels.create({
          school_id: schoolId,
          name: values.name as string,
          order_index: values.order_index === "" ? undefined : Number(values.order_index),
        })
      }
      onUpdate={(id, values) =>
        educationLevels.update(id, {
          name: values.name as string,
          order_index: values.order_index === "" ? undefined : Number(values.order_index),
        })
      }
      onItemCreated={() => list.retry()}
      onItemUpdated={() => list.retry()}
      />
    </div>
  );
}

function SubjectsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => subjects.list(schoolId), [schoolId]);
  if (list.isLoading) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<Subject>
      title="Matières"
      items={list.data}
      fields={SUBJECT_FIELDS}
      canManage={canManage}
      onCreate={(values) => subjects.create({ school_id: schoolId, name: values.name as string, code: (values.code as string) || null })}
      onUpdate={(id, values) => subjects.update(id, { name: values.name as string, code: (values.code as string) || null })}
      onItemCreated={() => list.retry()}
      onItemUpdated={() => list.retry()}
      />
    </div>
  );
}

function RoomsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => rooms.list(schoolId), [schoolId]);
  if (list.isLoading) return <p className="text-sm text-slate-400">Chargement...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  return (
    <div className="flex flex-col gap-3">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ResourceCrudPanel<Room>
      title="Salles"
      items={list.data}
      fields={ROOM_FIELDS}
      canManage={canManage}
      onCreate={(values) =>
        rooms.create({ school_id: schoolId, name: values.name as string, capacity: values.capacity === "" ? undefined : Number(values.capacity) })
      }
      onUpdate={(id, values) =>
        rooms.update(id, { name: values.name as string, capacity: values.capacity === "" ? undefined : Number(values.capacity) })
      }
      onItemCreated={() => list.retry()}
      onItemUpdated={() => list.retry()}
      />
    </div>
  );
}

const TABS = ["Années", "Niveaux", "Matières", "Salles", "Classes"] as const;
type Tab = (typeof TABS)[number];

export default function AcademicsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("academics.manage");
  const [tab, setTab] = useState<Tab>("Années");

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Configuration académique</h1>

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

      {tab === "Années" && <AcademicYearsPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Niveaux" && <EducationLevelsPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Matières" && <SubjectsPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Salles" && <RoomsPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Classes" && <ClassesPanel schoolId={currentSchoolId} canManage={canManage} />}
    </div>
  );
}
