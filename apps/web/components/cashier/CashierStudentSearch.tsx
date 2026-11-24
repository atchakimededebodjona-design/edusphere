"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { searchRoster } from "@/lib/cashier/offline";
import { cashier, type CashierRoster, type CashierStudent } from "@/lib/fees/client";

const MIN_SEARCH_LENGTH = 2;
const DEBOUNCE_MS = 300;
const MAX_RESULTS = 20;

// Pas de réponse du serveur (appareil hors ligne, ou aucune copie de cette recherche précise).
function serverUnreachable(err: unknown): boolean {
  return !(err instanceof ApiError) || err.status === 0 || err.status === 502 || err.status === 503 || err.status === 504;
}

/** Recherche d'élève du poste de caisse — `GET /cashier/students/search` (projection minimale),
 * jamais `GET /students` (le CAISSIER n'a pas `students.read`).
 *
 * Phase 32, lot 3 — sans internet, la recherche se fait dans la liste gardée sur l'appareil
 * (`roster`, téléchargée quand la caisse est ouverte). */
export function CashierStudentSearch({
  schoolId,
  onSelect,
  roster = null,
  offline = false,
}: {
  schoolId: string;
  onSelect: (student: CashierStudent) => void;
  roster?: CashierRoster | null;
  offline?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<CashierStudent[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fromRoster, setFromRoster] = useState(false);
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
    const searchLocally = (): boolean => {
      if (!roster) return false;
      setResults(searchRoster(roster, trimmed, MAX_RESULTS));
      setFromRoster(true);
      setError(null);
      return true;
    };
    if (offline) {
      setIsSearching(false);
      if (!searchLocally()) {
        setResults(null);
        setError(
          "Sans internet, la recherche se fait dans la liste des élèves gardée sur cet appareil, et elle n'y est pas : ouvrez la page Caisse avec internet, caisse ouverte, avant une coupure.",
        );
      }
      return;
    }
    setIsSearching(true);
    const timer = window.setTimeout(() => {
      cashier
        .searchStudents(schoolId, trimmed, MAX_RESULTS)
        .then((found) => {
          if (latestRequest.current !== requestId) return;
          setResults(found);
          setFromRoster(false);
          setError(null);
        })
        .catch((err) => {
          if (latestRequest.current !== requestId) return;
          if (serverUnreachable(err) && searchLocally()) return;
          setResults(null);
          setError(toErrorMessage(err));
        })
        .finally(() => {
          if (latestRequest.current === requestId) setIsSearching(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [term, schoolId, roster, offline]);

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
          className="w-full min-h-12 rounded-lg border border-slate-300 bg-white px-4 text-base font-normal text-slate-900 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
        />
      </label>

      {term.trim().length > 0 && term.trim().length < MIN_SEARCH_LENGTH && (
        <p className="text-xs text-slate-600">Saisissez au moins {MIN_SEARCH_LENGTH} caractères.</p>
      )}
      {isSearching && <p className="text-xs text-slate-600">Recherche...</p>}
      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {results !== null && fromRoster && roster && (
        <p data-testid="cash-search-from-roster" className="text-xs text-amber-800">
          Recherche dans la liste gardée sur cet appareil (élèves ayant encore des frais à payer
          {roster.truncated ? ", liste incomplète" : ""}).
        </p>
      )}
      {results !== null && !isSearching && results.length === 0 && (
        <p className="text-sm text-slate-600">Aucun élève trouvé.</p>
      )}

      {results !== null && results.length > 0 && (
        <ul aria-label="Résultats de recherche" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {results.map((student) => (
            <li
              key={student.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="min-w-0 text-sm">
                <p className="truncate font-semibold text-slate-900">
                  {student.last_name} {student.first_name}
                </p>
                <p className="text-xs text-slate-600">
                  {student.matricule}
                  {student.current_class_name ? ` · ${student.current_class_name}` : " · Classe non renseignée"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => onSelect(student)}
                aria-label={`Sélectionner ${student.last_name} ${student.first_name}`}
                className="inline-flex min-h-11 shrink-0 items-center rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 sm:min-h-9 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
              >
                Sélectionner
              </button>
            </li>
          ))}
        </ul>
      )}
      {results !== null && results.length === MAX_RESULTS && (
        <p className="text-xs text-slate-600">
          Seuls les {MAX_RESULTS} premiers résultats sont affichés : précisez la recherche.
        </p>
      )}
    </section>
  );
}
