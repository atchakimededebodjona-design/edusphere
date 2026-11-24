"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ExistingSchoolsList, NewSchoolForm, schoolAddedMessage } from "@/components/enrollment/NewSchoolForm";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { addPartnerSchool, listPartnerOrganizations } from "@/lib/partners/client";

// PR #19 — parcours PARTNER_ADMIN « organisation existante ». La liste vient de
// GET /partner/organizations, qui ne renvoie QUE les organisations où ce partenaire a déjà au moins
// une école inscrite (aucune recherche/énumération de la plateforme). L'ajout passe par
// POST /partner/organizations/{id}/schools, qui revérifie ce périmètre côté API (404 sinon) — ce
// composant n'est jamais la protection.
export function ExistingOrganizationEnroll({ onEnrolled }: { onEnrolled: () => void }) {
  const { data, error, isLoading, retry } = useAsyncData(listPartnerOrganizations, []);
  const [selectedId, setSelectedId] = useState<string>("");

  if (error) return <ErrorRetry message={error} onRetry={retry} />;
  if (isLoading || !data) return <p className="text-sm text-slate-600">Chargement de vos organisations...</p>;
  if (data.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        Aucune organisation dans votre périmètre : inscrivez d&apos;abord une école avec « Nouvelle organisation ».
      </p>
    );
  }

  const selected = data.find((org) => org.organization_id === selectedId) ?? null;
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <label className="flex flex-col gap-1 text-sm text-slate-700">
        Organisation
        <select
          className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 max-w-md"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          <option value="">— Choisir une de vos organisations —</option>
          {data.map((org) => (
            <option key={org.organization_id} value={org.organization_id}>
              {org.organization_name}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <section className="flex flex-col gap-3" aria-label="Organisation sélectionnée">
          <p className="text-lg font-semibold text-slate-900">{selected.organization_name}</p>
          <ExistingSchoolsList schools={selected.schools.map((s) => ({ id: s.school_id, name: s.school_name }))} />
          <NewSchoolForm
            organizationName={selected.organization_name}
            existingSchoolNames={selected.schools.map((s) => s.school_name)}
            onSubmit={async (payload) => {
              const added = await addPartnerSchool(selected.organization_id, payload);
              retry();
              onEnrolled();
              return schoolAddedMessage(added, "inscrit dans");
            }}
          />
        </section>
      )}
    </div>
  );
}
