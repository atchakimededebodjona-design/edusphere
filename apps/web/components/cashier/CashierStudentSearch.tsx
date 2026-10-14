"use client";

import { useEffect, useRef, useState } from "react";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { cashier, type CashierStudent } from "@/lib/fees/client";

const MIN_SEARCH_LENGTH = 2;
const DEBOUNCE_MS = 300;
const MAX_RESULTS = 20;

/** Recherche d'élève du poste de caisse — `GET /cashier/students/search` (projection minimale),
 * jamais `GET /students` (le CAISSIER n'a pas `students.read`). */
export function CashierStudentSearch({
  schoolId,
  onSelect,
}: {
  schoolId: string;
  onSelect: (student: CashierStudent) => void;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<CashierStudent[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Seule la réponse de la DERNIÈRE recherche lancée est affichée (frappe rapide, réponses désordonnées).
  const latestRequest = useRef(0);

  useEffect(() => {
    const trimmed = term.trim();
    if (trimmed.length < MIN_SEARCH_LENGTH) {
      latestRequest.current += 1;
      setResults(null);
      setIsSearching(false);
      setError(null);
      return;
    }
    const requestId = ++latestRequest.current;
    setIsSearching(true);
    const timer = window.setTimeout(() => {
      cashier
        .searchStudents(schoolId, trimmed, MAX_RESULTS)
        .then((found) => {
          if (latestRequest.current !== requestId) return;
          setResults(found);
          setError(null);
        })
        .catch((err) => {
          if (latestRequest.current !== requestId) return;
          setResults(null);
          setError(toErrorMessage(err));
        })
        .finally(() => {
          if (latestRequest.current === requestId) setIsSearching(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [term, schoolId]);

  return (
    <section className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
        Rechercher un élève par nom, prénom ou matricule
        <input
          type="search"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Ex. : Ama, Koffi, EL-CM1-002"
          autoComplete="off"
          autoFocus
          className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-base font-normal"
        />
      </label>

      {term.trim().length > 0 && term.trim().length < MIN_SEARCH_LENGTH && (
        <p className="text-xs text-slate-500">Saisissez au moins {MIN_SEARCH_LENGTH} caractères.</p>
      )}
      {isSearching && <p className="text-xs text-slate-500">Recherche...</p>}
      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {results !== null && !isSearching && results.length === 0 && (
        <p className="text-sm text-slate-500">Aucun élève trouvé.</p>
      )}

      {results !== null && results.length > 0 && (
        <ul aria-label="Résultats de recherche" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {results.map((student) => (
            <li
              key={student.id}
              className="flex items-center justify-between gap-3 rounded border border-slate-200 bg-white p-3"
            >
              <div className="min-w-0 text-sm">
                <p className="truncate font-semibold text-slate-900">
                  {student.last_name} {student.first_name}
                </p>
                <p className="text-xs text-slate-500">
                  {student.matricule}
                  {student.current_class_name ? ` · ${student.current_class_name}` : " · Classe non renseignée"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => onSelect(student)}
                aria-label={`Sélectionner ${student.last_name} ${student.first_name}`}
                className="shrink-0 rounded bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700"
              >
                Sélectionner
              </button>
            </li>
          ))}
        </ul>
      )}
      {results !== null && results.length === MAX_RESULTS && (
        <p className="text-xs text-slate-500">
          Seuls les {MAX_RESULTS} premiers résultats sont affichés : précisez la recherche.
        </p>
      )}
    </section>
  );
}
