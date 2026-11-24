"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
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
import { filterSchoolTeachers } from "@/lib/academics/teachers";

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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forThisSubject = assignments.filter((a) => a.class_subject_id === classSubjectId);
  const teacherName = (userId: string) => teachers.find((t) => t.user.id === userId)?.user.full_name ?? userId;

  function startEdit(assignment: TeacherAssignment) {
    setEditingId(assignment.id);
    setSelectedTeacherId(assignment.user_id);
    setError(null);
  }

  function stopEdit() {
    setEditingId(null);
    setSelectedTeacherId("");
  }

  async function handleAssign(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedTeacherId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await teacherAssignments.create(classId, {
        user_id: selectedTeacherId,
        subject_id: subjectId,
      });
      onAssignmentsChange([...assignments, created]);
      stopEdit();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(assignmentId: string, event: React.FormEvent) {
    event.preventDefault();
    if (!selectedTeacherId) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await teacherAssignments.update(classId, assignmentId, { user_id: selectedTeacherId });
      onAssignmentsChange(assignments.map((a) => (a.id === assignmentId ? updated : a)));
      stopEdit();
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

  const teacherSelect = (
    <select
      value={selectedTeacherId}
      onChange={(e) => setSelectedTeacherId(e.target.value)}
      required
      className="block min-h-9 rounded-lg border border-slate-300 bg-white px-2 text-sm text-slate-900 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
      aria-label="Enseignant"
    >
      <option value="">Aucun enseignant</option>
      {teachers.map((t) => (
        <option key={t.user.id} value={t.user.id}>
          {t.user.full_name}
        </option>
      ))}
    </select>
  );

  return (
    <div className="ml-4 mt-1 flex flex-col gap-1 border-l border-slate-200 pl-3 text-xs">
      {forThisSubject.map((a) =>
        editingId === a.id ? (
          <form key={a.id} onSubmit={(e) => handleUpdate(a.id, e)} className="flex items-center gap-2">
            {teacherSelect}
            <button type="submit" disabled={busy} className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary-600 px-3 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
              Enregistrer
            </button>
            <button type="button" onClick={stopEdit} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
              Annuler
            </button>
          </form>
        ) : (
          <div key={a.id} className="flex items-center justify-between gap-2">
            <span>Enseignant : {teacherName(a.user_id)}</span>
            {canManage && (
              <span className="flex gap-2">
                <button type="button" onClick={() => startEdit(a)} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                  Modifier
                </button>
                <button type="button" onClick={() => handleRemove(a.id)} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                  Retirer
                </button>
              </span>
            )}
          </div>
        ),
      )}
      {forThisSubject.length === 0 && <span className="text-slate-600">Aucun enseignant affecté.</span>}
      {canManage && forThisSubject.length === 0 && teachers.length === 0 && (
        <span className="text-amber-700">
          Aucun enseignant actif rattaché à cette école : créez un utilisateur avec le rôle Enseignant.
        </span>
      )}
      {canManage && forThisSubject.length === 0 && teachers.length > 0 && (
        <form onSubmit={handleAssign} className="flex items-center gap-2">
          {teacherSelect}
          <button type="submit" disabled={busy || !selectedTeacherId} className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary-600 px-3 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
            Affecter
          </button>
        </form>
      )}
      {error && <p className="text-red-700">{error}</p>}
    </div>
  );
}

export function ClassSubjectsEditor({
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [teachers, setTeachers] = useState<UserWithRoles[]>([]);

  const loadClassSubjects = useCallback(() => {
    setAttached(null);
    setLoadError(null);
    Promise.all([
      classSubjects.list(schoolClass.id),
      teacherAssignments.list(schoolClass.id),
      usersClient.list(schoolId),
    ])
      .then(([attachedResult, assignmentsResult, allUsers]) => {
        setAttached(attachedResult);
        setAssignments(assignmentsResult);
        setTeachers(filterSchoolTeachers(allUsers, schoolId));
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolClass.id, schoolId]);

  useEffect(() => {
    loadClassSubjects();
  }, [loadClassSubjects]);

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

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadClassSubjects} />;
  if (attached === null) return <p className="text-sm text-slate-600">Chargement des matières...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-base font-bold text-slate-900">Matières de {schoolClass.name}</h3>
      <ul className="flex flex-col gap-1">
        {attached.map((a) => {
          const subject = subjects.find((s) => s.id === a.subject_id);
          return (
            <li key={a.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
              <div className="flex items-center justify-between">
                <span>
                  {subject?.name ?? a.subject_id} — coefficient {a.coefficient}
                </span>
                {canManage && (
                  <button type="button" onClick={() => handleRemove(a.id)} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
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
        {attached.length === 0 && <li className="text-sm text-slate-600">Aucune matière attachée.</li>}
      </ul>
      {canManage && available.length > 0 && (
        <form onSubmit={handleAdd} className="flex items-end gap-3">
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Matière
            <select
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            >
              <option value="">—</option>
              {available.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Coefficient
            <input
              type="number"
              min="0"
              step="0.5"
              value={coefficient}
              onChange={(e) => setCoefficient(e.target.value)}
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 !w-24"
            />
          </label>
          <button type="submit" disabled={busy} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
            Ajouter
          </button>
        </form>
      )}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadAll = useCallback(() => {
    setLoadError(null);
    Promise.all([
      academicYears.list(schoolId),
      educationLevels.list(schoolId),
      subjectsClient.list(schoolId),
      schoolClasses.list(schoolId),
    ])
      .then(([y, l, s, c]) => {
        setYears(y);
        setLevels(l);
        setSubjects(s);
        setClasses(c);
        setSelectedYearId(y.find((year) => year.is_current)?.id ?? y[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

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

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadAll} />;
  if (years === null || levels === null || subjects === null || classes === null) {
    return <p className="text-sm text-slate-600">Chargement...</p>;
  }

  if (years.length === 0) {
    return <p className="text-sm text-slate-600">Créez d&apos;abord une année scolaire dans l&apos;onglet « Années ».</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm font-medium text-slate-800 w-full sm:w-72">
        Année scolaire
        <select
          value={selectedYearId}
          onChange={(e) => {
            setSelectedYearId(e.target.value);
            setSelectedClassId(null);
          }}
          className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
        >
          {years.map((y) => (
            <option key={y.id} value={y.id}>
              {y.name}
            </option>
          ))}
        </select>
      </label>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Nom</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Niveau</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Capacité</th>
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
                    className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Voir les matières
                  </button>
                </td>
              </tr>
            ))}
            {classesForYear.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-slate-600">
                  Aucune classe pour cette année.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Nom
            <input
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Niveau
            <select
              value={form.education_level_id}
              onChange={(e) => setForm((prev) => ({ ...prev, education_level_id: e.target.value }))}
              required
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
            >
              <option value="">—</option>
              {levels.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Capacité
            <input
              type="number"
              value={form.capacity}
              onChange={(e) => setForm((prev) => ({ ...prev, capacity: e.target.value }))}
              className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 !w-28"
            />
          </label>
          <button type="submit" disabled={creating} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
            {creating ? "Ajout..." : "Ajouter"}
          </button>
        </form>
      )}
      {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

      {selectedClass && (
        <ClassSubjectsEditor schoolId={schoolId} schoolClass={selectedClass} subjects={subjects} canManage={canManage} />
      )}
    </div>
  );
}
