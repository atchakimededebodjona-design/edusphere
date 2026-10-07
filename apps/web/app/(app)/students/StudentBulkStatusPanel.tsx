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
    <div role="dialog" aria-label="Modifier en masse" className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">
        Modifier en masse — {selectedIds.length} élève{selectedIds.length > 1 ? "s" : ""} sélectionné{selectedIds.length > 1 ? "s" : ""}
      </h2>
      <form onSubmit={handleApply} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Nouveau statut
          <select
            value={targetStatus}
            onChange={(e) => setTargetStatus(e.target.value as StudentStatus)}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-xs text-slate-600">
          Motif du changement de statut
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex. Inscription nouvelle année"
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Application..." : "Appliquer"}
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
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
