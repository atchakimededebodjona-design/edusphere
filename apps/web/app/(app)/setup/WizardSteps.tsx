"use client";

import { useEffect, useMemo, useState } from "react";
import { ClassSubjectsEditor } from "@/app/(app)/academics/ClassesPanel";
import {
  academicTerms,
  academicYears,
  educationLevels,
  schoolClasses,
  subjects as subjectsClient,
  type AcademicTerm,
  type AcademicYear,
  type EducationLevel,
  type SchoolClass,
  type Subject,
} from "@/lib/academics/client";
import { formatWizardError } from "@/lib/wizard/errors";

const inputClass = "rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100";
const labelClass = "flex flex-col gap-1 text-xs text-slate-600";
const primaryButtonClass = "rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50";

export function StepError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </p>
  );
}

// --- Step 1 : année scolaire ---------------------------------------------------------------
export function StepYear({
  schoolId,
  selectedYearId,
  onSelectYear,
}: {
  schoolId: string;
  selectedYearId: string;
  onSelectYear: (year: AcademicYear) => void;
}) {
  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "", is_current: false });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    academicYears
      .list(schoolId)
      .then(setYears)
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await academicYears.create({ school_id: schoolId, ...form });
      setYears((prev) => [...(prev ?? []), created]);
      onSelectYear(created);
      setForm({ name: "", start_date: "", end_date: "", is_current: false });
    } catch (err) {
      setError(formatWizardError(err));
    } finally {
      setCreating(false);
    }
  }

  if (loadError) return <StepError message={loadError} />;
  if (years === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Choisissez l&apos;année scolaire à configurer, ou créez-en une nouvelle. Les étapes suivantes
        (termes, classes) s&apos;appliqueront à cette année.
      </p>

      {years.length > 0 && (
        <fieldset className="flex flex-col gap-2" aria-label="Années existantes">
          <legend className="text-sm font-medium text-slate-900">Années existantes</legend>
          {years.map((year) => (
            <label
              key={year.id}
              className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm ${
                selectedYearId === year.id ? "border-slate-900 bg-slate-50" : "border-slate-200"
              }`}
            >
              <input
                type="radio"
                name="academic-year"
                checked={selectedYearId === year.id}
                onChange={() => onSelectYear(year)}
              />
              {year.name} ({year.start_date} → {year.end_date}) {year.is_current && "· en cours"}
            </label>
          ))}
        </fieldset>
      )}

      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
        <label className={labelClass}>
          Nom
          <input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
            placeholder="2026-2027"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Début
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => setForm((prev) => ({ ...prev, start_date: e.target.value }))}
            required
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Fin
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => setForm((prev) => ({ ...prev, end_date: e.target.value }))}
            required
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-1.5 pb-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={form.is_current}
            onChange={(e) => setForm((prev) => ({ ...prev, is_current: e.target.checked }))}
          />
          Année en cours
        </label>
        <button type="submit" disabled={creating} className={primaryButtonClass}>
          {creating ? "Création..." : "Créer cette année"}
        </button>
      </form>
      <StepError message={error} />
    </div>
  );
}

// --- Step 2 : termes / périodes -------------------------------------------------------------
export function StepTerms({ yearId }: { yearId: string }) {
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "", order_index: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setTerms(null);
    setLoadError(null);
    academicTerms
      .list(yearId)
      .then(setTerms)
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [yearId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await academicTerms.create({
        academic_year_id: yearId,
        name: form.name,
        start_date: form.start_date,
        end_date: form.end_date,
        order_index: form.order_index === "" ? undefined : Number(form.order_index),
      });
      setTerms((prev) => [...(prev ?? []), created]);
      setForm({ name: "", start_date: "", end_date: "", order_index: "" });
    } catch (err) {
      setError(formatWizardError(err));
    } finally {
      setCreating(false);
    }
  }

  if (loadError) return <StepError message={loadError} />;
  if (terms === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Découpez l&apos;année en termes ou trimestres (ex. Trimestre 1, 2, 3). Ils seront utilisés pour
        les évaluations, présences et bulletins.
      </p>

      <ul className="flex flex-col gap-1">
        {terms.map((t) => (
          <li key={t.id} className="rounded border border-slate-200 px-3 py-2 text-sm">
            {t.name} ({t.start_date} → {t.end_date})
          </li>
        ))}
        {terms.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
            Aucun terme pour cette année pour l&apos;instant — ajoutez-en au moins un ci-dessous avant de
            passer à la saisie des présences/notes plus tard.
          </li>
        )}
      </ul>

      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
        <label className={labelClass}>
          Nom
          <input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
            placeholder="Trimestre 1"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Début
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => setForm((prev) => ({ ...prev, start_date: e.target.value }))}
            required
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Fin
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => setForm((prev) => ({ ...prev, end_date: e.target.value }))}
            required
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Ordre
          <input
            type="number"
            value={form.order_index}
            onChange={(e) => setForm((prev) => ({ ...prev, order_index: e.target.value }))}
            className={`${inputClass} w-20`}
          />
        </label>
        <button type="submit" disabled={creating} className={primaryButtonClass}>
          {creating ? "Création..." : "Ajouter ce terme"}
        </button>
      </form>
      <StepError message={error} />
    </div>
  );
}

// --- Step 3 : niveaux -------------------------------------------------------------------------
export function StepLevels({ schoolId }: { schoolId: string }) {
  const [levels, setLevels] = useState<EducationLevel[] | null>(null);
  const [form, setForm] = useState({ name: "", order_index: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    educationLevels
      .list(schoolId)
      .then(setLevels)
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await educationLevels.create({
        school_id: schoolId,
        name: form.name,
        order_index: form.order_index === "" ? undefined : Number(form.order_index),
      });
      setLevels((prev) => [...(prev ?? []), created]);
      setForm({ name: "", order_index: "" });
    } catch (err) {
      setError(formatWizardError(err));
    } finally {
      setCreating(false);
    }
  }

  if (loadError) return <StepError message={loadError} />;
  if (levels === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Les niveaux (ex. CP, CE1, 6e...) seront utilisés pour organiser vos classes à l&apos;étape
        suivante.
      </p>
      <ul className="flex flex-col gap-1">
        {levels.map((l) => (
          <li key={l.id} className="rounded border border-slate-200 px-3 py-2 text-sm">
            {l.name}
          </li>
        ))}
        {levels.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
            Aucun niveau pour l&apos;instant — vous en aurez besoin pour créer une classe.
          </li>
        )}
      </ul>
      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
        <label className={labelClass}>
          Nom
          <input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
            placeholder="CE1"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Ordre
          <input
            type="number"
            value={form.order_index}
            onChange={(e) => setForm((prev) => ({ ...prev, order_index: e.target.value }))}
            className={`${inputClass} w-20`}
          />
        </label>
        <button type="submit" disabled={creating} className={primaryButtonClass}>
          {creating ? "Création..." : "Ajouter ce niveau"}
        </button>
      </form>
      <StepError message={error} />
    </div>
  );
}

// --- Step 4 : matières ------------------------------------------------------------------------
export function StepSubjects({ schoolId }: { schoolId: string }) {
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [form, setForm] = useState({ name: "", code: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    subjectsClient
      .list(schoolId)
      .then(setSubjects)
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await subjectsClient.create({ school_id: schoolId, name: form.name, code: form.code || null });
      setSubjects((prev) => [...(prev ?? []), created]);
      setForm({ name: "", code: "" });
    } catch (err) {
      setError(formatWizardError(err));
    } finally {
      setCreating(false);
    }
  }

  if (loadError) return <StepError message={loadError} />;
  if (subjects === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Les matières enseignées (ex. Mathématiques, Français...) seront attachées à vos classes à
        l&apos;étape des affectations enseignants.
      </p>
      <ul className="flex flex-col gap-1">
        {subjects.map((s) => (
          <li key={s.id} className="rounded border border-slate-200 px-3 py-2 text-sm">
            {s.name} {s.code && <span className="text-slate-400">({s.code})</span>}
          </li>
        ))}
        {subjects.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
            Aucune matière pour l&apos;instant.
          </li>
        )}
      </ul>
      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
        <label className={labelClass}>
          Nom
          <input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
            placeholder="Mathématiques"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Code
          <input
            value={form.code}
            onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value }))}
            placeholder="MATH"
            className={inputClass}
          />
        </label>
        <button type="submit" disabled={creating} className={primaryButtonClass}>
          {creating ? "Création..." : "Ajouter cette matière"}
        </button>
      </form>
      <StepError message={error} />
    </div>
  );
}

// --- Step 5 : classes --------------------------------------------------------------------------
export function StepClasses({ schoolId, yearId }: { schoolId: string; yearId: string }) {
  const [levels, setLevels] = useState<EducationLevel[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [form, setForm] = useState({ name: "", education_level_id: "", capacity: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([educationLevels.list(schoolId), schoolClasses.list(schoolId)])
      .then(([l, c]) => {
        setLevels(l);
        setClasses(c);
      })
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId]);

  const classesForYear = useMemo(() => (classes ?? []).filter((c) => c.academic_year_id === yearId), [classes, yearId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!form.education_level_id) return;
    setCreating(true);
    setError(null);
    try {
      const created = await schoolClasses.create({
        academic_year_id: yearId,
        education_level_id: form.education_level_id,
        name: form.name,
        capacity: form.capacity === "" ? undefined : Number(form.capacity),
      });
      setClasses((prev) => [...(prev ?? []), created]);
      setForm({ name: "", education_level_id: "", capacity: "" });
    } catch (err) {
      setError(formatWizardError(err));
    } finally {
      setCreating(false);
    }
  }

  if (loadError) return <StepError message={loadError} />;
  if (levels === null || classes === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  if (levels.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
        Aucun niveau n&apos;a encore été créé — revenez à l&apos;étape « Niveaux » avant de créer une
        classe.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">Créez les classes de cette année scolaire.</p>
      <ul className="flex flex-col gap-1">
        {classesForYear.map((c) => (
          <li key={c.id} className="rounded border border-slate-200 px-3 py-2 text-sm">
            {c.name} — {levels.find((l) => l.id === c.education_level_id)?.name ?? "—"}
          </li>
        ))}
        {classesForYear.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
            Aucune classe pour cette année pour l&apos;instant.
          </li>
        )}
      </ul>
      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
        <label className={labelClass}>
          Nom
          <input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
            placeholder="CE1-A"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Niveau
          <select
            value={form.education_level_id}
            onChange={(e) => setForm((prev) => ({ ...prev, education_level_id: e.target.value }))}
            required
            className={inputClass}
          >
            <option value="">—</option>
            {levels.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          Capacité
          <input
            type="number"
            value={form.capacity}
            onChange={(e) => setForm((prev) => ({ ...prev, capacity: e.target.value }))}
            className={`${inputClass} w-24`}
          />
        </label>
        <button type="submit" disabled={creating} className={primaryButtonClass}>
          {creating ? "Création..." : "Ajouter cette classe"}
        </button>
      </form>
      <StepError message={error} />
    </div>
  );
}

// --- Step 6 : affectations enseignants ----------------------------------------------------------
export function StepAssignments({ schoolId, yearId }: { schoolId: string; yearId: string }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([schoolClasses.list(schoolId), subjectsClient.list(schoolId)])
      .then(([c, s]) => {
        setClasses(c);
        setSubjects(s);
      })
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId]);

  const classesForYear = useMemo(() => (classes ?? []).filter((c) => c.academic_year_id === yearId), [classes, yearId]);
  const selectedClass = classesForYear.find((c) => c.id === selectedClassId) ?? null;

  if (loadError) return <StepError message={loadError} />;
  if (classes === null || subjects === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  if (classesForYear.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
        Aucune classe pour cette année — revenez à l&apos;étape « Classes » avant d&apos;affecter des
        enseignants.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Pour chaque classe, attachez les matières enseignées puis affectez un enseignant à chacune.
      </p>
      <label className="flex w-fit flex-col gap-1 text-xs text-slate-600">
        Classe
        <select
          value={selectedClassId}
          onChange={(e) => setSelectedClassId(e.target.value)}
          className={inputClass}
        >
          <option value="">—</option>
          {classesForYear.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {selectedClass && (
        <ClassSubjectsEditor schoolId={schoolId} schoolClass={selectedClass} subjects={subjects} canManage />
      )}
    </div>
  );
}

// --- Step 7 : résumé ----------------------------------------------------------------------------
export function StepSummary({
  schoolId,
  year,
  onGoToStep,
}: {
  schoolId: string;
  year: AcademicYear;
  onGoToStep: (step: number) => void;
}) {
  const [counts, setCounts] = useState<{
    terms: number;
    levels: number;
    subjects: number;
    classes: number;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      academicTerms.list(year.id),
      educationLevels.list(schoolId),
      subjectsClient.list(schoolId),
      schoolClasses.list(schoolId),
    ])
      .then(([terms, levels, subjects, classes]) => {
        setCounts({
          terms: terms.length,
          levels: levels.length,
          subjects: subjects.length,
          classes: classes.filter((c) => c.academic_year_id === year.id).length,
        });
      })
      .catch((err) => setLoadError(formatWizardError(err)));
  }, [schoolId, year.id]);

  const rows: { label: string; value: string; step: number }[] = [
    { label: "Année scolaire", value: year.name, step: 0 },
    { label: "Termes", value: counts ? `${counts.terms}` : "…", step: 1 },
    { label: "Niveaux", value: counts ? `${counts.levels}` : "…", step: 2 },
    { label: "Matières", value: counts ? `${counts.subjects}` : "…", step: 3 },
    { label: "Classes (cette année)", value: counts ? `${counts.classes}` : "…", step: 4 },
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
        Configuration de l&apos;école — {year.name}
      </p>
      <StepError message={loadError} />
      <ul className="flex flex-col gap-1">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center justify-between rounded border border-slate-200 px-3 py-2 text-sm">
            <span>
              {row.label} : <strong>{row.value}</strong>
            </span>
            <button type="button" onClick={() => onGoToStep(row.step)} className="text-xs text-slate-700 underline">
              Modifier
            </button>
          </li>
        ))}
      </ul>
      <p className="text-sm text-slate-600">
        Vous pouvez revenir sur n&apos;importe quelle section ci-dessus, ou depuis la page{" "}
        <span className="font-medium">Académique</span> à tout moment. Les affectations enseignants
        peuvent être complétées progressivement au fil de l&apos;arrivée des enseignants.
      </p>
    </div>
  );
}
