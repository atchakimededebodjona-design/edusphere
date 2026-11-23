"use client";

import { ButtonLink } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { PageHeader, Skeleton, StatCard } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { getPartnerDashboard } from "@/lib/partners/client";

// PR #17 — accueil de l'espace partenaire. Les chiffres ne portent que sur les écoles inscrites par
// CE partenaire (filtrage fait côté API, jamais ici). Refonte, phase 2 (2026-11-23) : présentation.
export default function PartnerHomePage() {
  const { data, error, isLoading, retry } = useAsyncData(getPartnerDashboard, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Espace partenaire"
        description="Suivez les écoles que vous avez inscrites sur EduLinkage."
        actions={<ButtonLink href="/partner/schools">+ Inscrire une école</ButtonLink>}
      />
      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-hidden="true">
          {[0, 1].map((index) => (
            <div key={index} className="rounded-xl border border-slate-200 bg-white p-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-2 h-7 w-16" />
            </div>
          ))}
        </div>
      )}
      {data && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <StatCard icon="school" label="Écoles inscrites" value={String(data.school_count)} href="/partner/schools" />
          <StatCard icon="building" label="Organisations" value={String(data.organization_count)} />
        </div>
      )}
    </div>
  );
}
