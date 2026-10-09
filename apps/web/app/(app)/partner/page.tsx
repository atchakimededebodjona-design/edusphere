"use client";

import Link from "next/link";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { getPartnerDashboard } from "@/lib/partners/client";

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

// PR #17 — accueil de l'espace partenaire. Les chiffres ne portent que sur les écoles inscrites par
// CE partenaire (filtrage fait côté API, jamais ici).
export default function PartnerHomePage() {
  const { data, error, isLoading, retry } = useAsyncData(getPartnerDashboard, []);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Espace partenaire</h1>
      <p className="text-slate-600">Suivez les écoles que vous avez inscrites sur EduLinkage.</p>
      <div>
        <Link
          href="/partner/schools"
          className="inline-flex rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95"
        >
          + Inscrire une école
        </Link>
      </div>
      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement des indicateurs...</p>}
      {data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <MetricCard label="Écoles inscrites" value={String(data.school_count)} />
          <MetricCard label="Organisations" value={String(data.organization_count)} />
        </div>
      )}
    </div>
  );
}
