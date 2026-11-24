"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ExistingSchoolsList, NewSchoolForm, schoolAddedMessage } from "@/components/enrollment/NewSchoolForm";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import {
  addPlatformSchool,
  getPlatformOrganizationSchools,
  listPlatformOrganizations,
  type PlatformOrganization,
  type PlatformOrganizationSchools,
} from "@/lib/platform/client";

// PR #19 — parcours PLATFORM_OWNER « organisation existante » : rechercher/sélectionner une
// organisation, voir ses établissements, puis en ajouter un (POST
// /platform/organizations/{id}/schools). Contrôle réel côté API (permission
// `platform.schools.enroll`) ; ce composant ne crée jamais d'organisation.
export function ExistingOrganizationPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlatformOrganization[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PlatformOrganizationSchools | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  async function search(event?: React.FormEvent) {
    event?.preventDefault();
    setSearching(true);
    setSearchError(null);
    try {
      const page = await listPlatformOrganizations(1, 20, query);
      setResults(page.items);
    } catch (err) {
      setSearchError(toErrorMessage(err));
    } finally {
      setSearching(false);
    }
  }

  const loadDetail = useCallback(async (organizationId: string) => {
    setDetailError(null);
    try {
      setDetail(await getPlatformOrganizationSchools(organizationId));
    } catch (err) {
      setDetail(null);
      setDetailError(toErrorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={search} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Rechercher une organisation existante
          <input
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 sm:!w-72"
            placeholder="Nom ou identifiant de l'organisation"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button type="submit" disabled={searching} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
          {searching ? "Recherche..." : "Rechercher"}
        </button>
      </form>
      {searchError && <ErrorRetry message={searchError} onRetry={() => void search()} />}
      {results && results.length === 0 && <p className="text-sm text-slate-600">Aucune organisation trouvée.</p>}
      {results && results.length > 0 && (
        <ul className="flex flex-col gap-1" aria-label="Organisations trouvées">
          {results.map((org) => (
            <li key={org.id}>
              <button
                type="button"
                onClick={() => setSelectedId(org.id)}
                aria-pressed={selectedId === org.id}
                className={`w-full max-w-md rounded border px-3 py-2 text-left text-sm ${
                  selectedId === org.id ? "border-slate-900 bg-slate-100" : "border-slate-300 hover:bg-slate-50"
                }`}
              >
                {org.name} <span className="text-slate-600">({org.slug})</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {detailError && selectedId && <ErrorRetry message={detailError} onRetry={() => void loadDetail(selectedId)} />}
      {detail && (
        <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5" aria-label="Organisation sélectionnée">
          <div>
            <p className="text-sm text-slate-600">Organisation sélectionnée</p>
            <p className="text-lg font-semibold text-slate-900">{detail.organization.name}</p>
          </div>
          <ExistingSchoolsList schools={detail.schools} />
          <NewSchoolForm
            organizationName={detail.organization.name}
            existingSchoolNames={detail.schools.map((school) => school.name)}
            onSubmit={async (payload) => {
              const added = await addPlatformSchool(detail.organization.id, payload);
              await loadDetail(detail.organization.id);
              return schoolAddedMessage(added);
            }}
          />
        </section>
      )}
    </div>
  );
}
