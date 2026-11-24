"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { Button } from "@/components/ui/Button";
import { DataTable, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { SelectField, TextField } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Badge, Card, EmptyState, PageHeader, type Tone } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatDateFR } from "@/lib/format/date";
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

const STATUS_TONES: Record<StudentStatus, Tone> = {
  ACTIVE: "success",
  INACTIVE: "neutral",
  GRADUATED: "info",
  WITHDRAWN: "warning",
  TRANSFERRED: "neutral",
};

const SEX_LABELS: Record<Sex, string> = { F: "Féminin", M: "Masculin" };

const initialForm = {
  matricule: "",
  first_name: "",
  last_name: "",
  date_of_birth: "",
  sex: "F" as Sex,
  place_of_birth: "",
  address: "",
};

/** Valeur stabilisée après `delay` ms sans changement : la recherche part quand on s'arrête de taper. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

const checkboxClass = "h-5 w-5 rounded border-slate-400 accent-primary-600";

export default function StudentsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("students.manage");

  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim(), 300);
  const [statusFilter, setStatusFilter] = useState<StudentStatus | "">("");
  const [classFilter, setClassFilter] = useState("");
  const [form, setForm] = useState(initialForm);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
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
        search: debouncedSearch || undefined,
        status: statusFilter || undefined,
        classId: classFilter && classFilter !== UNASSIGNED_FILTER ? classFilter : undefined,
        unassignedOnly: classFilter === UNASSIGNED_FILTER,
      }),
    [currentSchoolId, debouncedSearch, statusFilter, classFilter],
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
    setCreated(null);
    try {
      await students.create({ school_id: currentSchoolId, ...form });
      setCreated(`${form.first_name} ${form.last_name}`.trim());
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

  const items = list.data ?? [];
  const allSelected = items.length > 0 && selected.size === items.length;
  const set = (key: keyof typeof initialForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const columns: Column<Student>[] = [
    ...(canManage
      ? [
          {
            key: "select",
            header: (
              <label className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" checked={allSelected} onChange={() => toggleAll(items)} className={checkboxClass} />
                <span className="sm:sr-only">Tout sélectionner</span>
              </label>
            ),
            headerOnMobile: true,
            mobile: "lead" as const,
            cell: (s: Student) => (
              <input
                type="checkbox"
                aria-label={`Sélectionner ${s.first_name} ${s.last_name}`}
                checked={selected.has(s.id)}
                onChange={() => toggleOne(s.id)}
                className={`${checkboxClass} max-sm:mt-0.5`}
              />
            ),
          },
        ]
      : []),
    {
      key: "matricule",
      header: "Matricule",
      mobile: "title",
      cell: (s) => (
        <Link href={`/students/${s.id}`} className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800">
          {s.matricule}
        </Link>
      ),
    },
    { key: "first_name", header: "Prénom", cell: (s) => s.first_name },
    { key: "last_name", header: "Nom", cell: (s) => s.last_name },
    { key: "birth", header: "Date de naissance", cell: (s) => formatDateFR(s.date_of_birth) },
    { key: "sex", header: "Sexe", cell: (s) => SEX_LABELS[s.sex] },
    {
      key: "class",
      header: "Classe",
      cell: (s) => (currentYear === null ? "—" : (s.current_class_name ?? <span className="text-amber-800">Non affecté</span>)),
    },
    { key: "status", header: "Statut", cell: (s) => <Badge tone={STATUS_TONES[s.status]}>{STATUS_LABELS[s.status]}</Badge> },
    {
      key: "action",
      header: "Action",
      mobile: "full",
      cell: (s) =>
        canManage ? (
          <Link
            href={`/students/${s.id}`}
            className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 max-sm:-ml-2"
          >
            Modifier
          </Link>
        ) : null,
    },
  ];

  if (list.data === null && list.error) return <ErrorRetry message={list.error} onRetry={list.retry} />;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Élèves"
        description={list.data === null ? undefined : `${items.length} élève${items.length > 1 ? "s" : ""} dans cette liste.`}
        actions={
          canManage && (
            <a href="#nouvel-eleve" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 sm:min-h-10">
              <Icon name="plus" className="h-4 w-4" />
              Nouvel élève
            </a>
          )
        }
      />

      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}

      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField
            label="Rechercher"
            type="search"
            placeholder="Nom, prénom ou matricule"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SelectField label="Filtrer par statut" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StudentStatus | "")}>
            <option value="">Tous statuts</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          <div className="flex flex-col gap-1">
            <SelectField label="Filtrer par classe" value={classFilter} onChange={(e) => setClassFilter(e.target.value)}>
              <option value="">Toutes les classes</option>
              {/* "Non affectés" n'a de sens que relativement à une année scolaire courante : sans
                  elle, le concept n'existe pas — désactivé plutôt que de laisser croire qu'il
                  filtrerait correctement (voir aussi le garde-fou côté backend, qui renvoie [] si
                  ce filtre est quand même forcé sans année courante). */}
              <option value={UNASSIGNED_FILTER} disabled={!currentYear}>
                Non affectés
              </option>
              {classesForFilter.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </SelectField>
            {years !== null && !currentYear && (
              <span className="text-xs text-slate-600" data-testid="no-current-year-notice">
                Aucune année scolaire courante définie.
              </span>
            )}
          </div>
        </div>
      </Card>

      {canManage && selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3">
          <span className="text-sm font-medium text-primary-900">
            {selected.size} élève{selected.size > 1 ? "s" : ""} sélectionné{selected.size > 1 ? "s" : ""}
          </span>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setBulkPanelOpen(true)}>
              Modifier en masse
            </Button>
            <Button size="sm" onClick={() => setBulkEnrollmentPanelOpen(true)}>
              Affecter à une classe
            </Button>
          </div>
        </div>
      )}

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

      {!currentSchoolId || list.isLoading ? (
        <TableSkeleton />
      ) : (
        <DataTable
          caption="Élèves"
          columns={columns}
          rows={items}
          rowKey={(s) => s.id}
          rowTone={(s) => (selected.has(s.id) ? "highlight" : undefined)}
          empty={
            <EmptyState
              icon="student"
              title="Aucun élève."
              description={
                debouncedSearch || statusFilter || classFilter
                  ? "Aucun élève ne correspond à ces filtres."
                  : canManage
                    ? "Ajoutez un élève ci-dessous ou importez une liste."
                    : undefined
              }
            />
          }
        />
      )}

      {canManage && currentSchoolId && <StudentImportForm schoolId={currentSchoolId} onImported={() => list.retry()} />}

      {canManage && (
        <form id="nouvel-eleve" onSubmit={handleCreate} className="scroll-mt-20">
          <Card className="flex flex-col gap-4">
            <h2 className="text-lg font-bold text-slate-900">Nouvel élève</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <TextField label="Matricule" value={form.matricule} onChange={set("matricule")} required autoComplete="off" />
              <TextField label="Prénom" value={form.first_name} onChange={set("first_name")} required autoComplete="off" />
              <TextField label="Nom" value={form.last_name} onChange={set("last_name")} required autoComplete="off" />
              <TextField label="Date de naissance" type="date" value={form.date_of_birth} onChange={set("date_of_birth")} required />
              <SelectField label="Sexe" value={form.sex} onChange={set("sex")}>
                <option value="F">Féminin</option>
                <option value="M">Masculin</option>
              </SelectField>
              <TextField label="Lieu de naissance" value={form.place_of_birth} onChange={set("place_of_birth")} hint="Facultatif" />
              <TextField label="Adresse" value={form.address} onChange={set("address")} hint="Facultatif" />
            </div>
            {error && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {error}
              </p>
            )}
            {created && !error && (
              <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                {created} a été ajouté à la liste des élèves.
              </p>
            )}
            <Button type="submit" icon="plus" disabled={creating} className="self-start">
              {creating ? "Ajout..." : "Ajouter l'élève"}
            </Button>
          </Card>
        </form>
      )}
    </div>
  );
}
