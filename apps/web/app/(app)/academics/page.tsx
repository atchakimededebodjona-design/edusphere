"use client";

import { useEffect, useState } from "react";
import { ResourceCrudPanel, type FieldSpec } from "@/components/crud/ResourceCrudPanel";
import { educationLevels, rooms, subjects, type EducationLevel, type Room, type Subject } from "@/lib/academics/client";
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
  const [items, setItems] = useState<EducationLevel[] | null>(null);
  useEffect(() => {
    void educationLevels.list(schoolId).then(setItems);
  }, [schoolId]);
  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;
  return (
    <ResourceCrudPanel<EducationLevel>
      title="Niveaux"
      items={items}
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
      onItemCreated={(item) => setItems((prev) => [...(prev ?? []), item])}
      onItemUpdated={(item) => setItems((prev) => (prev ?? []).map((i) => (i.id === item.id ? item : i)))}
    />
  );
}

function SubjectsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [items, setItems] = useState<Subject[] | null>(null);
  useEffect(() => {
    void subjects.list(schoolId).then(setItems);
  }, [schoolId]);
  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;
  return (
    <ResourceCrudPanel<Subject>
      title="Matières"
      items={items}
      fields={SUBJECT_FIELDS}
      canManage={canManage}
      onCreate={(values) => subjects.create({ school_id: schoolId, name: values.name as string, code: (values.code as string) || null })}
      onUpdate={(id, values) => subjects.update(id, { name: values.name as string, code: (values.code as string) || null })}
      onItemCreated={(item) => setItems((prev) => [...(prev ?? []), item])}
      onItemUpdated={(item) => setItems((prev) => (prev ?? []).map((i) => (i.id === item.id ? item : i)))}
    />
  );
}

function RoomsPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [items, setItems] = useState<Room[] | null>(null);
  useEffect(() => {
    void rooms.list(schoolId).then(setItems);
  }, [schoolId]);
  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;
  return (
    <ResourceCrudPanel<Room>
      title="Salles"
      items={items}
      fields={ROOM_FIELDS}
      canManage={canManage}
      onCreate={(values) =>
        rooms.create({ school_id: schoolId, name: values.name as string, capacity: values.capacity === "" ? undefined : Number(values.capacity) })
      }
      onUpdate={(id, values) =>
        rooms.update(id, { name: values.name as string, capacity: values.capacity === "" ? undefined : Number(values.capacity) })
      }
      onItemCreated={(item) => setItems((prev) => [...(prev ?? []), item])}
      onItemUpdated={(item) => setItems((prev) => (prev ?? []).map((i) => (i.id === item.id ? item : i)))}
    />
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
