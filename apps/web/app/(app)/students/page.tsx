"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { students, type Sex, type Student, type StudentStatus } from "@/lib/students/client";
import { StudentImportForm } from "@/app/(app)/students/StudentImportForm";
import { StudentBulkStatusPanel } from "@/app/(app)/students/StudentBulkStatusPanel";
import { StudentBulkEnrollmentPanel } from "@/app/(app)/students/StudentBulkEnrollmentPanel";

const UNASSIGNED_FILTER = "__unassigned__";

const STATUS_LABELS: Record<StudentStatus, string> = {
  ACTIVE: "Actif",
  INACTIVE: "Inactif",
  GRADUATED: "Diplômé",
  WITHDRAWN: "Retiré",
  TRANSFERRED: "Transféré",
};

const SEX_LABELS: Record<Sex, string> = { F: "Féminin", M: "Masculin" };

// "2015-03-18" -> "18/03/2015". Le backend renvoie toujours une date ISO (date_of_birth: date) ;
// un format invalide resterait tel quel plutôt que de planter l'affichage.
function formatDateFR(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : isoDate;
}

const initialForm = {
  matricule: "",
  first_name: "",
  last_name: "",
  date_of_birth: "",
  sex: "F" as Sex,
  place_of_birth: "",
  address: "",
};

export default function StudentsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("students.manage");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StudentStatus | "">("");
  const [classFilter, setClassFilter] = useState("");
  const [form, setForm] = useState(initialForm);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkPanelOpen, setBulkPanelOpen] = useState(false);
  const [bulkEnrollmentPanelOpen, setBulkEnrollmentPanelOpen] = useState(false);

  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  useEffect(() => {
    if (!currentSchoolId) return;
    Promise.all([academicYears.list(currentSchoolId), schoolClasses.list(currentSchoolId)])
      .then(([yearsResult, classesResult]) => {
        setYears(yearsResult);
        setClasses(classesResult);
      })
      .catch(() => undefined);
  }, [currentSchoolId]);
  const currentYear = years?.find((y) => y.is_current) ?? null;
  // Le filtre "Classe" ne propose que les classes de l'année scolaire courante — cohérent avec la
  // colonne Classe de la liste, qui ne reflète elle aussi que cette année-là.
  const classesForFilter = currentYear ? (classes ?? []).filter((c) => c.academic_year_id === currentYear.id) : [];

  const list = useAsyncData(
    () =>
      students.list(currentSchoolId ?? "", {
        search: search || undefined,
        status: statusFilter || undefined,
        classId: classFilter && classFilter !== UNASSIGNED_FILTER ? classFilter : undefined,
        unassignedOnly: classFilter === UNASSIGNED_FILTER,
      }),
    [currentSchoolId, search, statusFilter, classFilter],
    { enabled: Boolean(currentSchoolId) },
  );

  // La sélection ne doit jamais porter sur une ligne qui n'est plus affichée (changement de
  // filtre, rechargement après modification en masse) — voir section "Sélection et pagination".
  useEffect(() => {
    if (list.data === null) return;
    const visibleIds = new Set(list.data.map((s) => s.id));
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => visibleIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [list.data]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setCreating(true);
    setError(null);
    try {
      await students.create({ school_id: currentSchoolId, ...form });
      setForm(initialForm);
      list.retry();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll(items: Student[]) {
    setSelected((prev) => (prev.size === items.length ? new Set() : new Set(items.map((s) => s.id))));
  }

  if (!currentSchoolId || list.isLoading) return <p className="text-sm text-slate-500">Chargement...</p>;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  const items = list.data;
  const allSelected = items.length > 0 && selected.size === items.length;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Élèves</h1>

      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}

      <div className="flex flex-wrap items-center gap-3">
        <input
          placeholder="Rechercher (nom, matricule)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StudentStatus | "")}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Tous statuts</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
          aria-label="Filtrer par classe"
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Toutes les classes</option>
          <option value={UNASSIGNED_FILTER}>Non affectés</option>
          {classesForFilter.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        {canManage && selected.size > 0 && (
          <>
            <span className="text-sm text-slate-600">
              {selected.size} élève{selected.size > 1 ? "s" : ""} sélectionné{selected.size > 1 ? "s" : ""}
            </span>
            <button
              type="button"
              onClick={() => setBulkPanelOpen(true)}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white"
            >
              Modifier en masse
            </button>
            <button
              type="button"
              onClick={() => setBulkEnrollmentPanelOpen(true)}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white"
            >
              Affecter à une classe
            </button>
          </>
        )}
      </div>

      {canManage && bulkPanelOpen && selected.size > 0 && (
        <StudentBulkStatusPanel
          selectedIds={[...selected]}
          onClose={() => setBulkPanelOpen(false)}
          onApplied={() => {
            setBulkPanelOpen(false);
            setSelected(new Set());
            list.retry();
          }}
        />
      )}

      {canManage && bulkEnrollmentPanelOpen && selected.size > 0 && currentSchoolId && (
        <StudentBulkEnrollmentPanel
          schoolId={currentSchoolId}
          selectedIds={[...selected]}
          onClose={() => setBulkEnrollmentPanelOpen(false)}
          onApplied={() => {
            setBulkEnrollmentPanelOpen(false);
            setSelected(new Set());
            list.retry();
          }}
        />
      )}

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {canManage && (
                <th className="px-3 py-2 text-left">
                  <input
                    type="checkbox"
                    aria-label="Tout sélectionner"
                    checked={allSelected}
                    onChange={() => toggleAll(items)}
                  />
                </th>
              )}
              <th className="px-3 py-2 text-left font-medium text-slate-600">Matricule</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Prénom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Date de naissance</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Sexe</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Classe</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.length === 0 ? (
              <tr>
                <td colSpan={canManage ? 9 : 8} className="px-3 py-4 text-center text-slate-400">
                  Aucun élève.
                </td>
              </tr>
            ) : (
              items.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50">
                  {canManage && (
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={`Sélectionner ${s.first_name} ${s.last_name}`}
                        checked={selected.has(s.id)}
                        onChange={() => toggleOne(s.id)}
                      />
                    </td>
                  )}
                  <td className="px-3 py-2">
                    <Link href={`/students/${s.id}`} className="text-slate-900 underline">
                      {s.matricule}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{s.first_name}</td>
                  <td className="px-3 py-2">{s.last_name}</td>
                  <td className="px-3 py-2">{formatDateFR(s.date_of_birth)}</td>
                  <td className="px-3 py-2">{SEX_LABELS[s.sex]}</td>
                  <td className="px-3 py-2">
                    {currentYear === null ? "—" : (s.current_class_name ?? "Non affecté")}
                  </td>
                  <td className="px-3 py-2">{STATUS_LABELS[s.status]}</td>
                  <td className="px-3 py-2">
                    {canManage && (
                      <Link href={`/students/${s.id}`} className="text-slate-900 underline">
                        Modifier
                      </Link>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {canManage && currentSchoolId && <StudentImportForm schoolId={currentSchoolId} onImported={() => list.retry()} />}

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-dashed border-slate-300 p-4">
          <h2 className="text-sm font-semibold text-slate-900">Nouvel élève</h2>
          <div className="flex flex-wrap gap-3">
            <input
              placeholder="Matricule"
              value={form.matricule}
              onChange={(e) => setForm((prev) => ({ ...prev, matricule: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Prénom"
              value={form.first_name}
              onChange={(e) => setForm((prev) => ({ ...prev, first_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Nom"
              value={form.last_name}
              onChange={(e) => setForm((prev) => ({ ...prev, last_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              type="date"
              value={form.date_of_birth}
              onChange={(e) => setForm((prev) => ({ ...prev, date_of_birth: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <select
              value={form.sex}
              onChange={(e) => setForm((prev) => ({ ...prev, sex: e.target.value as Sex }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="F">Féminin</option>
              <option value="M">Masculin</option>
            </select>
            <input
              placeholder="Lieu de naissance"
              value={form.place_of_birth}
              onChange={(e) => setForm((prev) => ({ ...prev, place_of_birth: e.target.value }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Adresse"
              value={form.address}
              onChange={(e) => setForm((prev) => ({ ...prev, address: e.target.value }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Ajout..." : "Ajouter"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      )}
    </div>
  );
}
