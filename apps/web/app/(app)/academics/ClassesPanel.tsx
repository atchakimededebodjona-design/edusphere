"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  classSubjects,
  educationLevels,
  schoolClasses,
  academicYears,
  subjects as subjectsClient,
  teacherAssignments,
  type ClassSubject,
  type EducationLevel,
  type SchoolClass,
  type AcademicYear,
  type Subject,
  type TeacherAssignment,
} from "@/lib/academics/client";
import { users as usersClient, type UserWithRoles } from "@/lib/users/client";

function TeacherAssignmentEditor({
  classId,
  classSubjectId,
  subjectId,
  assignments,
  teachers,
  canManage,
  onAssignmentsChange,
}: {
  classId: string;
  classSubjectId: string;
  subjectId: string;
  assignments: TeacherAssignment[];
  teachers: UserWithRoles[];
  canManage: boolean;
  onAssignmentsChange: (next: TeacherAssignment[]) => void;
}) {
  const [selectedTeacherId, setSelectedTeacherId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forThisSubject = assignments.filter((a) => a.class_subject_id === classSubjectId);
  const assignedUserIds = new Set(forThisSubject.map((a) => a.user_id));
  const available = teachers.filter((t) => !assignedUserIds.has(t.user.id));

  async function handleAssign(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedTeacherId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await teacherAssignments.create(classId, { user_id: selectedTeacherId, subject_id: subjectId });
      onAssignmentsChange([...assignments, created]);
      setSelectedTeacherId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(assignmentId: string) {
    setBusy(true);
    setError(null);
    try {
      await teacherAssignments.remove(classId, assignmentId);
      onAssignmentsChange(assignments.filter((a) => a.id !== assignmentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ml-4 mt-1 flex flex-col gap-1 border-l border-slate-200 pl-3 text-xs">
      {forThisSubject.map((a) => {
        const teacher = teachers.find((t) => t.user.id === a.user_id);
        return (
          <div key={a.id} className="flex items-center justify-between gap-2">
            <span>Enseignant : {teacher?.user.full_name ?? a.user_id}</span>
            {canManage && (
              <button type="button" onClick={() => handleRemove(a.id)} disabled={busy} className="text-red-700 underline">
                Retirer
              </button>
            )}
          </div>
        );
      })}
      {forThisSubject.length === 0 && <span className="text-slate-400">Aucun enseignant affecté.</span>}
      {canManage && available.length > 0 && (
        <form onSubmit={handleAssign} className="flex items-center gap-2">
          <select
            value={selectedTeacherId}
            onChange={(e) => setSelectedTeacherId(e.target.value)}
            required
            className="rounded border border-slate-300 px-1.5 py-0.5"
          >
            <option value="">—</option>
            {available.map((t) => (
              <option key={t.user.id} value={t.user.id}>
                {t.user.full_name}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-2 py-0.5 text-white disabled:opacity-50">
            Assigner
          </button>
        </form>
      )}
      {error && <p className="text-red-700">{error}</p>}
    </div>
  );
}

function ClassSubjectsEditor({
  schoolId,
  schoolClass,
  subjects,
  canManage,
}: {
  schoolId: string;
  schoolClass: SchoolClass;
  subjects: Subject[];
  canManage: boolean;
}) {
  const [attached, setAttached] = useState<ClassSubject[] | null>(null);
  const [subjectId, setSubjectId] = useState("");
  const [coefficient, setCoefficient] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [teachers, setTeachers] = useState<UserWithRoles[]>([]);

  useEffect(() => {
    void classSubjects.list(schoolClass.id).then(setAttached);
    void teacherAssignments.list(schoolClass.id).then(setAssignments);
    void usersClient.list(schoolId).then((all) => setTeachers(all.filter((u) => u.roles.some((r) => r.role_code === "TEACHER"))));
  }, [schoolClass.id, schoolId]);

  const available = useMemo(
    () => subjects.filter((s) => !attached?.some((a) => a.subject_id === s.id)),
    [subjects, attached],
  );

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!subjectId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await classSubjects.create(schoolClass.id, { subject_id: subjectId, coefficient: Number(coefficient) });
      setAttached((prev) => [...(prev ?? []), created]);
      setSubjectId("");
      setCoefficient("1");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(classSubjectId: string) {
    setBusy(true);
    setError(null);
    try {
      await classSubjects.remove(schoolClass.id, classSubjectId);
      setAttached((prev) => (prev ?? []).filter((a) => a.id !== classSubjectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  if (attached === null) return <p className="text-sm text-slate-400">Chargement des matières...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-900">Matières de {schoolClass.name}</h3>
      <ul className="flex flex-col gap-1">
        {attached.map((a) => {
          const subject = subjects.find((s) => s.id === a.subject_id);
          return (
            <li key={a.id} className="rounded border border-slate-200 px-3 py-1.5 text-sm">
              <div className="flex items-center justify-between">
                <span>
                  {subject?.name ?? a.subject_id} — coefficient {a.coefficient}
                </span>
                {canManage && (
                  <button type="button" onClick={() => handleRemove(a.id)} disabled={busy} className="text-xs text-red-700 underline">
                    Retirer
                  </button>
                )}
              </div>
              <TeacherAssignmentEditor
                classId={schoolClass.id}
                classSubjectId={a.id}
                subjectId={a.subject_id}
                assignments={assignments}
                teachers={teachers}
                canManage={canManage}
                onAssignmentsChange={setAssignments}
              />
            </li>
          );
        })}
        {attached.length === 0 && <li className="text-sm text-slate-400">Aucune matière attachée.</li>}
      </ul>
      {canManage && available.length > 0 && (
        <form onSubmit={handleAdd} className="flex items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Matière
            <select
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {available.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Coefficient
            <input
              type="number"
              min="0"
              step="0.5"
              value={coefficient}
              onChange={(e) => setCoefficient(e.target.value)}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Ajouter
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

export function ClassesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [levels, setLevels] = useState<EducationLevel[] | null>(null);
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [selectedYearId, setSelectedYearId] = useState("");
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", education_level_id: "", capacity: "" });
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void Promise.all([
      academicYears.list(schoolId),
      educationLevels.list(schoolId),
      subjectsClient.list(schoolId),
      schoolClasses.list(schoolId),
    ]).then(([y, l, s, c]) => {
      setYears(y);
      setLevels(l);
      setSubjects(s);
      setClasses(c);
      setSelectedYearId(y.find((year) => year.is_current)?.id ?? y[0]?.id ?? "");
    });
  }, [schoolId]);

  const classesForYear = useMemo(
    () => (classes ?? []).filter((c) => c.academic_year_id === selectedYearId),
    [classes, selectedYearId],
  );
  const selectedClass = classesForYear.find((c) => c.id === selectedClassId) ?? null;

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedYearId || !form.education_level_id) return;
    setCreating(true);
    setError(null);
    try {
      const created = await schoolClasses.create({
        academic_year_id: selectedYearId,
        education_level_id: form.education_level_id,
        name: form.name,
        capacity: form.capacity === "" ? undefined : Number(form.capacity),
      });
      setClasses((prev) => [...(prev ?? []), created]);
      setForm({ name: "", education_level_id: "", capacity: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (years === null || levels === null || subjects === null || classes === null) {
    return <p className="text-sm text-slate-400">Chargement...</p>;
  }

  if (years.length === 0) {
    return <p className="text-sm text-slate-500">Créez d&apos;abord une année scolaire dans l&apos;onglet « Années ».</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex w-fit flex-col gap-1 text-xs text-slate-600">
        Année scolaire
        <select
          value={selectedYearId}
          onChange={(e) => {
            setSelectedYearId(e.target.value);
            setSelectedClassId(null);
          }}
          className="rounded border border-slate-300 px-2 py-1 text-sm"
        >
          {years.map((y) => (
            <option key={y.id} value={y.id}>
              {y.name}
            </option>
          ))}
        </select>
      </label>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Niveau</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Capacité</th>
              <th className="w-24" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {classesForYear.map((c) => (
              <tr key={c.id} className={selectedClassId === c.id ? "bg-slate-50" : undefined}>
                <td className="px-3 py-2">{c.name}</td>
                <td className="px-3 py-2">{levels.find((l) => l.id === c.education_level_id)?.name ?? "—"}</td>
                <td className="px-3 py-2">{c.capacity ?? "—"}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setSelectedClassId(c.id)}
                    className="text-xs text-slate-700 underline"
                  >
                    Voir les matières
                  </button>
                </td>
              </tr>
            ))}
            {classesForYear.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-slate-400">
                  Aucune classe pour cette année.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
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
            Niveau
            <select
              value={form.education_level_id}
              onChange={(e) => setForm((prev) => ({ ...prev, education_level_id: e.target.value }))}
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
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Capacité
            <input
              type="number"
              value={form.capacity}
              onChange={(e) => setForm((prev) => ({ ...prev, capacity: e.target.value }))}
              className="w-24 rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={creating} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {creating ? "Ajout..." : "Ajouter"}
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}

      {selectedClass && (
        <ClassSubjectsEditor schoolId={schoolId} schoolClass={selectedClass} subjects={subjects} canManage={canManage} />
      )}
    </div>
  );
}
