"use client";

import { useEffect, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { students, type StudentBulkEnrollmentResult } from "@/lib/students/client";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type PreviewErrorKind = "capacity" | "permission" | "not_found" | "network" | "server";
type PreviewError = { kind: PreviewErrorKind; message: string };

// Seul un 409 est réellement une capacité/conflit — toute autre erreur (droits, ressource
// introuvable, réseau, serveur) doit rester distincte et jamais relabellisée "Capacité
// insuffisante" (voir correction post-audit : le code précédent traitait TOUTE previewError
// comme une capacité insuffisante, ce qui était trompeur pour un 403/404/réseau/500).
function describePreviewError(err: unknown): PreviewError {
  if (err instanceof ApiError) {
    if (err.status === 409) return { kind: "capacity", message: err.message };
    if (err.status === 403) return { kind: "permission", message: "Vous n'avez pas les droits nécessaires." };
    if (err.status === 404) return { kind: "not_found", message: "Classe, année scolaire ou élève introuvable." };
    return { kind: "server", message: "Une erreur serveur est survenue." };
  }
  // ApiError porte toujours un vrai statut HTTP reçu — son absence signifie qu'aucune réponse
  // n'est arrivée du tout (fetch() a rejeté : coupure réseau, DNS, CORS...).
  return { kind: "network", message: "Impossible de calculer l'aperçu. Vérifiez votre connexion." };
}

// Affectation en masse à une classe : sélectionne l'année + la classe, affiche un aperçu (capacité,
// répartition nouveaux/réaffectés/inchangés) calculé par le backend en dry-run AVANT toute écriture,
// puis confirme. Le backend reste l'autorité : cet aperçu ne fait que relayer son calcul, jamais une
// estimation côté client.
export function StudentBulkEnrollmentPanel({
  schoolId,
  selectedIds,
  onClose,
  onApplied,
}: {
  schoolId: string;
  selectedIds: string[];
  onClose: () => void;
  onApplied: () => void;
}) {
  const [years, setYears] = useState<AcademicYear[] | null>(null);
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [yearId, setYearId] = useState("");
  const [classId, setClassId] = useState("");
  const [enrollmentDate, setEnrollmentDate] = useState(today());

  const [preview, setPreview] = useState<StudentBulkEnrollmentResult | null>(null);
  const [previewError, setPreviewError] = useState<PreviewError | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [result, setResult] = useState<StudentBulkEnrollmentResult | null>(null);

  useEffect(() => {
    Promise.all([academicYears.list(schoolId), schoolClasses.list(schoolId)])
      .then(([yearsResult, classesResult]) => {
        setYears(yearsResult);
        setClasses(classesResult);
        const current = yearsResult.find((y) => y.is_current);
        if (current) setYearId(current.id);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId]);

  const classesForYear = (classes ?? []).filter((c) => c.academic_year_id === yearId);

  useEffect(() => {
    // La classe sélectionnée doit toujours appartenir à l'année actuellement choisie.
    if (classId && !classesForYear.some((c) => c.id === classId)) setClassId("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearId]);

  useEffect(() => {
    if (!yearId || !classId) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    students
      .bulkEnroll({ student_ids: selectedIds, academic_year_id: yearId, class_id: classId, enrollment_date: enrollmentDate }, true)
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setPreview(null);
        setPreviewError(describePreviewError(err));
      })
      .finally(() => {
        if (cancelled) return;
        setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearId, classId, enrollmentDate]);

  async function handleConfirm() {
    if (!yearId || !classId) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const data = await students.bulkEnroll({
        student_ids: selectedIds, academic_year_id: yearId, class_id: classId, enrollment_date: enrollmentDate,
      });
      setResult(data);
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setConfirming(false);
    }
  }

  const selectedYear = years?.find((y) => y.id === yearId);
  const selectedClass = classesForYear.find((c) => c.id === classId);
  const canConfirm = preview !== null && previewError === null && !previewLoading;

  if (result) {
    return (
      <div role="dialog" aria-label="Affecter des élèves à une classe" className="flex flex-col gap-4 rounded-xl border border-primary-200 bg-white p-4 shadow-sm sm:p-5">
        <h2 className="text-base font-bold text-slate-900">Affectation terminée</h2>
        <p className="text-sm text-slate-700" data-testid="bulk-enrollment-result-summary">
          {result.selected_count} élève{result.selected_count > 1 ? "s" : ""} traité{result.selected_count > 1 ? "s" : ""}
        </p>
        <ul className="text-sm text-slate-700">
          <li>{result.created_count} affecté{result.created_count > 1 ? "s" : ""}</li>
          <li>{result.reassigned_count} réaffecté{result.reassigned_count > 1 ? "s" : ""}</li>
          <li>{result.unchanged_count} déjà dans la classe</li>
        </ul>
        <button
          type="button"
          onClick={onApplied}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
          data-testid="bulk-enrollment-done"
        >
          Fermer
        </button>
      </div>
    );
  }

  return (
    <div role="dialog" aria-label="Affecter des élèves à une classe" className="flex flex-col gap-4 rounded-xl border border-primary-200 bg-white p-4 shadow-sm sm:p-5">
      <h2 className="text-base font-bold text-slate-900">
        Affecter des élèves à une classe — {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} sélectionné
        {selectedIds.length > 1 ? "s" : ""}
      </h2>

      {loadError && <p className="text-sm text-red-700">{loadError}</p>}

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Année scolaire
          <select
            value={yearId}
            onChange={(e) => setYearId(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">—</option>
            {(years ?? []).map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Classe
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            disabled={!yearId}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">—</option>
            {classesForYear.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Date d&apos;inscription
          <input
            type="date"
            value={enrollmentDate}
            onChange={(e) => setEnrollmentDate(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
      </div>

      {selectedYear && selectedClass && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700" data-testid="bulk-enrollment-preview">
          <p>
            Classe : <span className="font-medium">{selectedClass.name}</span> — Année :{" "}
            <span className="font-medium">{selectedYear.name}</span>
          </p>
          {previewLoading && <p className="text-slate-600">Calcul en cours...</p>}
          {preview && !previewLoading && (
            <>
              <p>Capacité : {preview.capacity ?? "Illimitée"}</p>
              <p>Effectif actuel : {preview.active_enrollment_count}</p>
              {preview.available_places !== null && <p>Places disponibles : {preview.available_places}</p>}
              <p>
                Sélection : {preview.selected_count} élève{preview.selected_count > 1 ? "s" : ""}
              </p>
              <p data-testid="bulk-enrollment-situation">
                {preview.created_count} nouveau{preview.created_count > 1 ? "x" : ""}, {preview.reassigned_count}{" "}
                réaffectation{preview.reassigned_count > 1 ? "s" : ""}, {preview.unchanged_count} déjà dans cette classe
              </p>
            </>
          )}
          {previewError && previewError.kind === "capacity" && (
            <p className="font-medium text-red-700" data-testid="bulk-enrollment-capacity-error">
              Capacité insuffisante — {previewError.message}
            </p>
          )}
          {previewError && previewError.kind !== "capacity" && (
            <p className="font-medium text-red-700" data-testid="bulk-enrollment-preview-error">
              {previewError.message}
            </p>
          )}
        </div>
      )}

      {selectedYear && selectedClass && preview && previewError === null && (
        <p className="text-sm text-slate-700">
          Vous êtes sur le point d&apos;affecter {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} à{" "}
          {selectedClass.name}.
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={!canConfirm || confirming}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
          data-testid="bulk-enrollment-confirm"
        >
          {confirming ? "Affectation en cours..." : "Confirmer l'affectation"}
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={confirming}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          Annuler
        </button>
      </div>
      {confirmError && (
        <p role="alert" className="text-sm text-red-700">
          {confirmError}
        </p>
      )}
    </div>
  );
}
