"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { students, type StudentImportReport } from "@/lib/students/client";

export function StudentImportForm({ schoolId, onImported }: { schoolId: string; onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState<StudentImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setImporting(true);
    setError(null);
    setReport(null);
    try {
      const result = await students.import(schoolId, file);
      setReport(result);
      setFile(null);
      if (result.created > 0) onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="rounded border border-dashed border-slate-300 p-4">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="text-sm font-semibold text-slate-900"
      >
        {open ? "▾" : "▸"} Importer des élèves (CSV/Excel)
      </button>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          <p className="text-xs text-slate-500">
            Colonnes requises : <code>matricule</code>, <code>first_name</code>, <code>last_name</code>,{" "}
            <code>date_of_birth</code> (AAAA-MM-JJ), <code>sex</code> (M/F). Les élèves déjà présents (même
            matricule, ou même prénom/nom/date de naissance) sont ignorés sans erreur.
          </p>
          <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
            <input
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
              className="text-sm"
            />
            <button
              type="submit"
              disabled={importing || !file}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {importing ? "Import..." : "Importer"}
            </button>
          </form>

          {error && <p className="text-sm text-red-700">{error}</p>}

          {report && (
            <div className="flex flex-col gap-3 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
              <p>
                {report.total_rows} ligne(s) — <strong>{report.created} créé(s)</strong>,{" "}
                {report.duplicates_skipped} doublon(s) ignoré(s), {report.errors.length} erreur(s).
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded border border-slate-200 bg-white p-2 text-center">
                  <p className="text-lg font-bold text-slate-900">{report.total_rows}</p>
                  <p className="text-xs text-slate-500">Total</p>
                </div>
                <div className="rounded border border-emerald-200 bg-emerald-50 p-2 text-center">
                  <p className="text-lg font-bold text-emerald-700">{report.created}</p>
                  <p className="text-xs text-emerald-700">Créés</p>
                </div>
                <div className="rounded border border-amber-200 bg-amber-50 p-2 text-center">
                  <p className="text-lg font-bold text-amber-700">{report.duplicates_skipped}</p>
                  <p className="text-xs text-amber-700">Doublons</p>
                </div>
                <div className="rounded border border-red-200 bg-red-50 p-2 text-center">
                  <p className="text-lg font-bold text-red-700">{report.errors.length}</p>
                  <p className="text-xs text-red-700">Erreurs</p>
                </div>
              </div>
              {report.created > 0 && (
                <p className="text-xs text-slate-500">
                  Les élèves importés ne sont pas automatiquement inscrits dans une classe : utilisez
                  « Inscriptions » sur la fiche de chaque élève, ou le module Académique.
                </p>
              )}
              {report.errors.length > 0 && (
                <ul className="flex flex-col gap-1 text-xs text-red-700">
                  {report.errors.map((e) => (
                    <li key={e.row}>
                      Ligne {e.row} : {e.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
