"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { students, type StudentStatus } from "@/lib/students/client";

const STATUS_OPTIONS: { value: StudentStatus; label: string }[] = [
  { value: "ACTIVE", label: "Actif" },
  { value: "INACTIVE", label: "Inactif" },
  { value: "GRADUATED", label: "Diplômé" },
  { value: "WITHDRAWN", label: "Retiré" },
  { value: "TRANSFERRED", label: "Transféré" },
];

// Modification en masse — STATUT uniquement. Les champs individuels (matricule, prénom, nom, date
// de naissance, sexe) n'ont pas leur place ici : ce sont des informations propres à chaque élève,
// jamais un changement collectif. Le cas d'usage visé est l'après-import : sélectionner plusieurs
// élèves fraîchement créés et les faire passer au bon statut en une fois.
export function StudentBulkStatusPanel({
  selectedIds,
  onClose,
  onApplied,
}: {
  selectedIds: string[];
  onClose: () => void;
  onApplied: () => void;
}) {
  const [targetStatus, setTargetStatus] = useState<StudentStatus>("ACTIVE");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApply(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await students.bulkUpdateStatus({
        student_ids: selectedIds,
        status: targetStatus,
        status_change_reason: reason.trim() || undefined,
      });
      onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-label="Modifier en masse" className="flex flex-col gap-4 rounded-xl border border-primary-200 bg-white p-4 shadow-sm sm:p-5">
      <h2 className="text-base font-bold text-slate-900">
        Modifier en masse — {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} sélectionné{selectedIds.length > 1 ? "s" : ""}
      </h2>
      <form onSubmit={handleApply} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Nouveau statut
          <select
            value={targetStatus}
            onChange={(e) => setTargetStatus(e.target.value as StudentStatus)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800 min-w-0 flex-1 sm:min-w-[16rem]">
          Motif du changement de statut
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex. Inscription nouvelle année"
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          {busy ? "Application..." : "Appliquer"}
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          Annuler
        </button>
      </form>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
