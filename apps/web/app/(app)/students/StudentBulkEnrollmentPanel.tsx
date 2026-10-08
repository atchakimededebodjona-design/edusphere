"use client";

import { useEffect, useState } from "react";
import { academicYears, schoolClasses, type AcademicYear, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { students, type StudentBulkEnrollmentResult } from "@/lib/students/client";

function today(): string {
  return new Date().toISOString().slice(0, 10);
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
  const [previewError, setPreviewError] = useState<string | null>(null);
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
        setPreviewError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
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
  const capacityInsufficient = previewError !== null;
  const canConfirm = preview !== null && !capacityInsufficient && !previewLoading;

  if (result) {
    return (
      <div role="dialog" aria-label="Affecter des élèves à une classe" className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Affectation terminée</h2>
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
          className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white"
          data-testid="bulk-enrollment-done"
        >
          Fermer
        </button>
      </div>
    );
  }

  return (
    <div role="dialog" aria-label="Affecter des élèves à une classe" className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">
        Affecter des élèves à une classe — {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} sélectionné
        {selectedIds.length > 1 ? "s" : ""}
      </h2>

      {loadError && <p className="text-sm text-red-700">{loadError}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Année scolaire
          <select
            value={yearId}
            onChange={(e) => setYearId(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">—</option>
            {(years ?? []).map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Classe
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            disabled={!yearId}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          >
            <option value="">—</option>
            {classesForYear.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Date d&apos;inscription
          <input
            type="date"
            value={enrollmentDate}
            onChange={(e) => setEnrollmentDate(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      {selectedYear && selectedClass && (
        <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700" data-testid="bulk-enrollment-preview">
          <p>
            Classe : <span className="font-medium">{selectedClass.name}</span> — Année :{" "}
            <span className="font-medium">{selectedYear.name}</span>
          </p>
          {previewLoading && <p className="text-slate-500">Calcul en cours...</p>}
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
          {capacityInsufficient && (
            <p className="font-medium text-red-700" data-testid="bulk-enrollment-capacity-error">
              Capacité insuffisante — {previewError}
            </p>
          )}
        </div>
      )}

      {selectedYear && selectedClass && preview && !capacityInsufficient && (
        <p className="text-sm text-slate-700">
          Vous êtes sur le point d&apos;affecter {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} à{" "}
          {selectedClass.name}.
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={!canConfirm || confirming}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          data-testid="bulk-enrollment-confirm"
        >
          {confirming ? "Affectation en cours..." : "Confirmer l'affectation"}
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={confirming}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
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
