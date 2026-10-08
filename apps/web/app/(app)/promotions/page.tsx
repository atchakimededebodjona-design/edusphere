"use client";

import { useEffect, useMemo, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { useAuth } from "@/lib/auth/useAuth";
import {
  students,
  type ClassMapping,
  type ExitType,
  type Student,
  type StudentBulkPromotionResult,
  type StudentExitDisposition,
  type StudentStatus,
} from "@/lib/students/client";

const EXIT_TYPE_LABELS: Record<ExitType, string> = {
  GRADUATED: "Sortie — Fin de cycle",
  TRANSFERRED: "Sortie — Transfert",
  WITHDRAWN: "Sortie — Retrait / abandon",
  OTHER: "Sortie — Autre",
};
const EXIT_TYPE_RESULT_LABELS: Record<ExitType, string> = {
  GRADUATED: "fin de cycle",
  TRANSFERRED: "transférés",
  WITHDRAWN: "retirés",
  OTHER: "autres",
};

type Step = "years" | "mapping" | "students" | "preview" | "result";

type PreviewErrorKind = "blocking" | "permission" | "not_found" | "network" | "server";
type PreviewError = { kind: PreviewErrorKind; message: string };

// Même distinction que StudentBulkEnrollmentPanel.tsx (correction post-audit du sprint
// précédent) : une erreur réseau/droits/ressource ne doit jamais être présentée comme un
// problème de capacité. Ici, un 409 ne survient QUE sur la confirmation réelle (le dry-run
// renvoie toujours 200 avec `blocking_errors` rempli — voir students/service.py::bulk_promote_students).
function describeError(err: unknown): PreviewError {
  if (err instanceof ApiError) {
    if (err.status === 409) return { kind: "blocking", message: err.message };
    if (err.status === 403) return { kind: "permission", message: "Vous n'avez pas les droits nécessaires." };
    if (err.status === 404) return { kind: "not_found", message: "Classe, année scolaire ou élève introuvable." };
    return { kind: "server", message: "Une erreur serveur est survenue." };
  }
  return { kind: "network", message: "Impossible de calculer l'aperçu. Vérifiez votre connexion." };
}

const STATUS_LABELS: Record<StudentStatus, string> = {
  ACTIVE: "Actif",
  INACTIVE: "Inactif",
  GRADUATED: "Diplômé",
  WITHDRAWN: "Retiré",
  TRANSFERRED: "Transféré",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function PromotionsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("students.manage");

  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [step, setStep] = useState<Step>("years");
  const [sourceYearId, setSourceYearId] = useState("");
  const [targetYearId, setTargetYearId] = useState("");
  // Par classe source : soit une classe cible (targetMapping), soit une disposition de sortie
  // (exitMapping) — jamais les deux à la fois (voir setTargetFor/setExitFor ci-dessous, qui
  // maintiennent cette exclusion mutuelle). Ni l'un ni l'autre = "Non traité" (explicite, jamais
  // un simple oubli silencieux — voir section aperçu).
  const [targetMapping, setTargetMapping] = useState<Record<string, string>>({});
  const [exitMapping, setExitMapping] = useState<Record<string, { exit_type: ExitType; reason: string }>>({});

  const [studentsBySourceClass, setStudentsBySourceClass] = useState<Record<string, Student[]>>({});
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [studentsError, setStudentsError] = useState<string | null>(null);
  const [classFilter, setClassFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StudentStatus | "">("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [enrollmentDate, setEnrollmentDate] = useState(today());
  const [preview, setPreview] = useState<StudentBulkPromotionResult | null>(null);
  const [previewError, setPreviewError] = useState<PreviewError | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<PreviewError | null>(null);
  const [result, setResult] = useState<StudentBulkPromotionResult | null>(null);

  useEffect(() => {
    if (!currentSchoolId) return;
    Promise.all([academicYears.list(currentSchoolId), schoolClasses.list(currentSchoolId)])
      .then(([yearsResult, classesResult]) => {
        setYears(yearsResult);
        setClasses(classesResult);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [currentSchoolId]);

  const sourceClasses = useMemo(
    () => (classes ?? []).filter((c) => c.academic_year_id === sourceYearId),
    [classes, sourceYearId],
  );
  const targetClasses = useMemo(
    () => (classes ?? []).filter((c) => c.academic_year_id === targetYearId),
    [classes, targetYearId],
  );
  const classMappings: ClassMapping[] = useMemo(
    () =>
      Object.entries(targetMapping)
        .filter(([, targetId]) => targetId)
        .map(([sourceId, targetId]) => ({ source_class_id: sourceId, target_class_id: targetId })),
    [targetMapping],
  );
  const exitDispositions: StudentExitDisposition[] = useMemo(
    () =>
      Object.entries(exitMapping)
        .filter(([sourceId]) => !targetMapping[sourceId])
        .map(([sourceId, disposition]) => ({
          source_class_id: sourceId,
          exit_type: disposition.exit_type,
          reason: disposition.reason || undefined,
        })),
    [exitMapping, targetMapping],
  );
  // "Non traité" explicite : ni classe cible, ni disposition de sortie pour cette classe source.
  const unmappedSourceClasses = sourceClasses.filter((c) => !targetMapping[c.id] && !exitMapping[c.id]);

  function setTargetFor(sourceClassId: string, targetClassId: string) {
    setTargetMapping((prev) => ({ ...prev, [sourceClassId]: targetClassId }));
    if (targetClassId) {
      // Une classe cible choisie annule toute disposition de sortie pour cette même classe
      // source — jamais les deux à la fois (section 6 : "Ne jamais permettre CM1 → CM2 +
      // Sortie simultanément").
      setExitMapping((prev) => {
        if (!(sourceClassId in prev)) return prev;
        const next = { ...prev };
        delete next[sourceClassId];
        return next;
      });
    }
  }

  function setExitFor(sourceClassId: string, exitType: ExitType | "") {
    if (!exitType) {
      setExitMapping((prev) => {
        if (!(sourceClassId in prev)) return prev;
        const next = { ...prev };
        delete next[sourceClassId];
        return next;
      });
      return;
    }
    setExitMapping((prev) => ({ ...prev, [sourceClassId]: { exit_type: exitType, reason: prev[sourceClassId]?.reason ?? "" } }));
  }

  function setExitReasonFor(sourceClassId: string, reason: string) {
    setExitMapping((prev) =>
      prev[sourceClassId] ? { ...prev, [sourceClassId]: { ...prev[sourceClassId], reason } } : prev,
    );
  }

  // --- Étape "students" : chargement par classe source, jamais un GET par élève (N+1) -----------
  async function loadStudentsForSourceClass(classId: string) {
    if (!currentSchoolId || studentsBySourceClass[classId]) return;
    setStudentsLoading(true);
    setStudentsError(null);
    try {
      const list = await students.list(currentSchoolId, { classId });
      setStudentsBySourceClass((prev) => ({ ...prev, [classId]: list }));
    } catch (err) {
      setStudentsError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setStudentsLoading(false);
    }
  }

  useEffect(() => {
    if (step !== "students") return;
    const classesToLoad = classFilter ? [classFilter] : sourceClasses.map((c) => c.id);
    classesToLoad.forEach((id) => void loadStudentsForSourceClass(id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, classFilter]);

  const visibleStudents = useMemo(() => {
    const classesToShow = classFilter ? [classFilter] : sourceClasses.map((c) => c.id);
    const all = classesToShow.flatMap((id) => studentsBySourceClass[id] ?? []);
    const deduped = Array.from(new Map(all.map((s) => [s.id, s])).values());
    return statusFilter ? deduped.filter((s) => s.status === statusFilter) : deduped;
  }, [classFilter, sourceClasses, studentsBySourceClass, statusFilter]);

  // Classe source de chaque élève affiché — nécessaire pour la colonne "Destination" (section 7),
  // calculée à partir des listes déjà chargées par classe (jamais une requête supplémentaire).
  const sourceClassIdByStudent = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [classId, list] of Object.entries(studentsBySourceClass)) {
      for (const s of list) map[s.id] = classId;
    }
    return map;
  }, [studentsBySourceClass]);

  function sourceClassNameForStudent(studentId: string): string {
    const classId = sourceClassIdByStudent[studentId];
    return sourceClasses.find((c) => c.id === classId)?.name ?? "—";
  }

  function destinationForStudent(studentId: string): string {
    const sourceClassId = sourceClassIdByStudent[studentId];
    if (!sourceClassId) return "—";
    const targetId = targetMapping[sourceClassId];
    if (targetId) return targetClasses.find((tc) => tc.id === targetId)?.name ?? "—";
    const disposition = exitMapping[sourceClassId];
    if (disposition) return EXIT_TYPE_LABELS[disposition.exit_type];
    return "Non traité";
  }

  function toggleStudent(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((prev) => {
      const visibleIds = visibleStudents.map((s) => s.id);
      const allSelected = visibleIds.length > 0 && visibleIds.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }

  // --- Étape "preview" : aperçu dry-run, recalculé à chaque changement de sélection/date --------
  useEffect(() => {
    if (step !== "preview" || selectedIds.size === 0) return;
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    students
      .bulkPromote(
        {
          source_academic_year_id: sourceYearId,
          target_academic_year_id: targetYearId,
          class_mappings: classMappings,
          exit_dispositions: exitDispositions,
          student_ids: [...selectedIds],
          enrollment_date: enrollmentDate,
        },
        true,
      )
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setPreview(null);
        setPreviewError(describeError(err));
      })
      .finally(() => {
        if (cancelled) return;
        setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, enrollmentDate]);

  async function handleConfirm() {
    setConfirming(true);
    setConfirmError(null);
    try {
      const data = await students.bulkPromote({
        source_academic_year_id: sourceYearId,
        target_academic_year_id: targetYearId,
        class_mappings: classMappings,
        exit_dispositions: exitDispositions,
        student_ids: [...selectedIds],
        enrollment_date: enrollmentDate,
      });
      setResult(data);
      setStep("result");
    } catch (err) {
      setConfirmError(describeError(err));
    } finally {
      setConfirming(false);
    }
  }

  function resetWizard() {
    setStep("years");
    setSourceYearId("");
    setTargetYearId("");
    setTargetMapping({});
    setExitMapping({});
    setStudentsBySourceClass({});
    setClassFilter("");
    setStatusFilter("");
    setSelectedIds(new Set());
    setEnrollmentDate(today());
    setPreview(null);
    setPreviewError(null);
    setConfirmError(null);
    setResult(null);
  }

  if (!canManage) {
    return <p className="text-sm text-red-700">Vous n&apos;avez pas accès à cette fonctionnalité.</p>;
  }
  if (loadError) return <ErrorRetry message={loadError} onRetry={() => window.location.reload()} />;
  if (!currentSchoolId || years === null || classes === null) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  const stepIndex = (["years", "mapping", "students", "preview", "result"] as Step[]).indexOf(step);

  return (
    <div className="flex w-full max-w-5xl min-w-0 flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Réinscriptions / Promotions</h1>

      <ol className="flex flex-wrap gap-2 text-xs text-slate-500" data-testid="promotion-steps">
        {["Années", "Mapping", "Élèves", "Aperçu", "Résultat"].map((label, i) => (
          <li
            key={label}
            className={`rounded-full border px-3 py-1 ${
              i <= stepIndex ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300"
            }`}
          >
            {label}
          </li>
        ))}
      </ol>

      {step === "years" && (
        <section className="flex flex-col gap-4 rounded border border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">1. Année source → Année cible</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Année source
              <select
                value={sourceYearId}
                onChange={(e) => setSourceYearId(e.target.value)}
                className="rounded border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">—</option>
                {years.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-600">
              Année cible
              <select
                value={targetYearId}
                onChange={(e) => setTargetYearId(e.target.value)}
                className="rounded border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">—</option>
                {years
                  .filter((y) => y.id !== sourceYearId)
                  .map((y) => (
                    <option key={y.id} value={y.id}>
                      {y.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <button
            type="button"
            onClick={() => setStep("mapping")}
            disabled={!sourceYearId || !targetYearId || sourceYearId === targetYearId}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            data-testid="promotion-years-next"
          >
            Suivant
          </button>
        </section>
      )}

      {step === "mapping" && (
        <section className="flex flex-col gap-4 rounded border border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">2. Correspondance des classes</h2>
          {sourceClasses.length === 0 ? (
            <p className="text-sm text-slate-400">Aucune classe pour l&apos;année source.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                    <th className="px-3 py-2 font-medium">Classe source</th>
                    <th className="px-3 py-2 font-medium">Destination</th>
                    <th className="px-3 py-2 font-medium">Capacité / action</th>
                  </tr>
                </thead>
                <tbody>
                  {sourceClasses.map((sc) => {
                    const targetId = targetMapping[sc.id] ?? "";
                    const targetClass = targetClasses.find((tc) => tc.id === targetId);
                    const disposition = exitMapping[sc.id];
                    return (
                      <tr key={sc.id} className="border-b border-slate-100">
                        <td className="px-3 py-2 align-top">{sc.name}</td>
                        <td className="px-3 py-2">
                          <div className="flex flex-col gap-2">
                            <select
                              value={targetId}
                              onChange={(e) => setTargetFor(sc.id, e.target.value)}
                              className="rounded border border-slate-300 px-2 py-1 text-sm"
                              aria-label={`Classe cible pour ${sc.name}`}
                            >
                              <option value="">Aucune correspondance</option>
                              {targetClasses.map((tc) => (
                                <option key={tc.id} value={tc.id}>
                                  {tc.name}
                                </option>
                              ))}
                            </select>
                            {!targetId && (
                              <select
                                value={disposition?.exit_type ?? ""}
                                onChange={(e) => setExitFor(sc.id, e.target.value as ExitType | "")}
                                className="rounded border border-slate-300 px-2 py-1 text-sm"
                                aria-label={`Disposition pour ${sc.name}`}
                              >
                                <option value="">Non traité</option>
                                {(Object.entries(EXIT_TYPE_LABELS) as [ExitType, string][]).map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            )}
                            {!targetId && disposition && (
                              <input
                                placeholder="Motif (facultatif)"
                                value={disposition.reason}
                                onChange={(e) => setExitReasonFor(sc.id, e.target.value)}
                                className="rounded border border-slate-300 px-2 py-1 text-xs"
                                aria-label={`Motif de sortie pour ${sc.name}`}
                              />
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-slate-500">
                          {targetClass
                            ? (targetClass.capacity ?? "Illimitée")
                            : disposition
                              ? EXIT_TYPE_LABELS[disposition.exit_type]
                              : "Non traité"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {unmappedSourceClasses.length > 0 && (
            <p className="text-sm text-amber-700" data-testid="promotion-unmapped-notice">
              Classes sans correspondance : {unmappedSourceClasses.map((c) => c.name).join(", ")}
            </p>
          )}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep("years")}
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
            >
              Précédent
            </button>
            <button
              type="button"
              onClick={() => setStep("students")}
              disabled={classMappings.length === 0 && exitDispositions.length === 0}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
              data-testid="promotion-mapping-next"
            >
              Suivant
            </button>
          </div>
        </section>
      )}

      {step === "students" && (
        <section className="flex flex-col gap-4 rounded border border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">3. Sélection des élèves</h2>
          <div className="flex flex-wrap gap-3">
            <select
              value={classFilter}
              onChange={(e) => setClassFilter(e.target.value)}
              aria-label="Filtrer par classe source"
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Toutes les classes source</option>
              {sourceClasses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StudentStatus | "")}
              aria-label="Filtrer par statut"
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Tous statuts</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {studentsError && <ErrorRetry message={studentsError} onRetry={() => loadStudentsForSourceClass(classFilter)} />}
          {studentsLoading && <p className="text-sm text-slate-500">Chargement des élèves...</p>}

          <div className="overflow-x-auto rounded border border-slate-200">
            <table className="w-full min-w-[500px] text-left text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Tout sélectionner"
                      checked={visibleStudents.length > 0 && visibleStudents.every((s) => selectedIds.has(s.id))}
                      onChange={toggleAllVisible}
                    />
                  </th>
                  <th className="px-3 py-2 font-medium text-slate-600">Matricule</th>
                  <th className="px-3 py-2 font-medium text-slate-600">Prénom</th>
                  <th className="px-3 py-2 font-medium text-slate-600">Nom</th>
                  <th className="px-3 py-2 font-medium text-slate-600">Classe source</th>
                  <th className="px-3 py-2 font-medium text-slate-600">Destination</th>
                  <th className="px-3 py-2 font-medium text-slate-600">Statut</th>
                </tr>
              </thead>
              <tbody>
                {visibleStudents.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-4 text-center text-slate-400">
                      Aucun élève.
                    </td>
                  </tr>
                ) : (
                  visibleStudents.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          aria-label={`Sélectionner ${s.first_name} ${s.last_name}`}
                          checked={selectedIds.has(s.id)}
                          onChange={() => toggleStudent(s.id)}
                        />
                      </td>
                      <td className="px-3 py-2">{s.matricule}</td>
                      <td className="px-3 py-2">{s.first_name}</td>
                      <td className="px-3 py-2">{s.last_name}</td>
                      <td className="px-3 py-2">{sourceClassNameForStudent(s.id)}</td>
                      <td className="px-3 py-2">{destinationForStudent(s.id)}</td>
                      <td className="px-3 py-2">{STATUS_LABELS[s.status]}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-600" data-testid="promotion-selected-count">
            {selectedIds.size} élève{selectedIds.size > 1 ? "s" : ""} sélectionné{selectedIds.size > 1 ? "s" : ""}
          </p>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep("mapping")}
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
            >
              Précédent
            </button>
            <button
              type="button"
              onClick={() => setStep("preview")}
              disabled={selectedIds.size === 0}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
              data-testid="promotion-students-next"
            >
              Suivant
            </button>
          </div>
        </section>
      )}

      {step === "preview" && (
        <section className="flex flex-col gap-4 rounded border border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">4. Aperçu</h2>
          <label className="flex w-fit flex-col gap-1 text-xs text-slate-600">
            Date d&apos;inscription
            <input
              type="date"
              value={enrollmentDate}
              onChange={(e) => setEnrollmentDate(e.target.value)}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          {previewLoading && <p className="text-sm text-slate-500">Calcul de l&apos;aperçu...</p>}

          {previewError && (
            <p className="text-sm font-medium text-red-700" data-testid="promotion-preview-error">
              {previewError.kind === "blocking" ? "Capacité insuffisante — " : ""}
              {previewError.message}
            </p>
          )}

          {preview && !previewLoading && (
            <div className="flex flex-col gap-3" data-testid="promotion-preview">
              <p>
                Total sélectionné : <span className="font-medium">{preview.selected_count}</span>
              </p>
              <ul className="text-sm text-slate-700">
                <li data-testid="promotion-preview-promoted">Promus : {preview.promoted_count}</li>
                <li data-testid="promotion-preview-repeated">Redoublants : {preview.repeated_count}</li>
                <li data-testid="promotion-preview-already">Déjà inscrits : {preview.already_enrolled_count}</li>
                <li data-testid="promotion-preview-exit">Sortants : {preview.exit_count}</li>
                <li data-testid="promotion-preview-unprocessed">
                  Sans classe cible et non traités : {preview.unprocessed_no_target_class_count}
                </li>
              </ul>

              {preview.exit_count > 0 && (
                <div className="rounded border border-slate-200 bg-slate-50 p-3" data-testid="promotion-exit-breakdown">
                  <p className="text-sm font-semibold text-slate-900">Sorties de l&apos;établissement</p>
                  <ul className="text-sm text-slate-700">
                    {(Object.entries(EXIT_TYPE_LABELS) as [ExitType, string][]).map(([type, label]) => (
                      <li key={type}>
                        {label.replace("Sortie — ", "")} : {preview.exit_counts_by_type[type] ?? 0}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {preview.unprocessed_no_target_class_count > 0 && (
                <p
                  className="rounded border border-red-300 bg-red-50 p-3 text-sm font-medium text-red-700"
                  data-testid="promotion-unprocessed-alert"
                >
                  {preview.unprocessed_no_target_class_count} élève(s) n&apos;ont ni classe cible ni disposition de
                  sortie.
                </p>
              )}

              {preview.class_previews.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[500px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                        <th className="px-3 py-2 font-medium">Classe cible</th>
                        <th className="px-3 py-2 font-medium">Capacité</th>
                        <th className="px-3 py-2 font-medium">Effectif actuel</th>
                        <th className="px-3 py-2 font-medium">Entrants</th>
                        <th className="px-3 py-2 font-medium">Places disponibles</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.class_previews.map((cp) => (
                        <tr key={cp.target_class_id} className="border-b border-slate-100">
                          <td className="px-3 py-2">{cp.target_class_name}</td>
                          <td className="px-3 py-2">{cp.capacity ?? "Illimitée"}</td>
                          <td className="px-3 py-2">{cp.active_enrollment_count}</td>
                          <td className="px-3 py-2">{cp.incoming_count}</td>
                          <td className="px-3 py-2">{cp.available_places ?? "Illimitées"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {preview.blocking_errors.length > 0 && (
                <ul className="text-sm font-medium text-red-700" data-testid="promotion-blocking-errors">
                  {preview.blocking_errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setStep("students")}
              disabled={confirming}
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              Précédent
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={
                confirming ||
                previewLoading ||
                preview === null ||
                previewError !== null ||
                preview.blocking_errors.length > 0 ||
                preview.unprocessed_no_target_class_count > 0
              }
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
              data-testid="promotion-confirm"
            >
              {confirming ? "Réinscription en cours..." : "Confirmer la réinscription"}
            </button>
          </div>
          {confirmError && (
            <p role="alert" className="text-sm text-red-700">
              {confirmError.kind === "blocking" ? "Capacité insuffisante — " : ""}
              {confirmError.message}
            </p>
          )}
        </section>
      )}

      {step === "result" && result && (
        <section className="flex flex-col gap-4 rounded border border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">Réinscription terminée</h2>
          <p className="text-sm text-slate-700" data-testid="promotion-result-summary">
            {result.selected_count} élève{result.selected_count > 1 ? "s" : ""} traité
            {result.selected_count > 1 ? "s" : ""}
          </p>
          <ul className="text-sm text-slate-700">
            <li>{result.promoted_count} promu{result.promoted_count > 1 ? "s" : ""}</li>
            <li>{result.repeated_count} redoublant{result.repeated_count > 1 ? "s" : ""}</li>
            <li>{result.already_enrolled_count} déjà inscrit{result.already_enrolled_count > 1 ? "s" : ""}</li>
            <li data-testid="promotion-result-exit">{result.exit_count} sortant{result.exit_count > 1 ? "s" : ""}</li>
            <li>{result.unprocessed_no_target_class_count} non traité{result.unprocessed_no_target_class_count > 1 ? "s" : ""}</li>
          </ul>
          {result.exit_count > 0 && (
            <ul className="text-sm text-slate-700" data-testid="promotion-result-exit-breakdown">
              {(Object.entries(EXIT_TYPE_RESULT_LABELS) as [ExitType, string][]).map(([type, label]) => (
                <li key={type}>
                  {result.exit_counts_by_type[type] ?? 0} {label}
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={resetWizard}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white"
            data-testid="promotion-done"
          >
            Nouvelle réinscription
          </button>
        </section>
      )}
    </div>
  );
}
