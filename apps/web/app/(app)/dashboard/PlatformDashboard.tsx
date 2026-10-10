"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { getPlatformDashboard, type PlatformDashboard as PlatformDashboardData } from "@/lib/platform/client";

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

export function PlatformDashboard() {
  const [dashboard, setDashboard] = useState<PlatformDashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setDashboard(null);
    setError(null);
    getPlatformDashboard()
      .then(setDashboard)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Administration de la plateforme</h1>
      <p className="text-slate-600">Bienvenue dans l&apos;espace d&apos;administration EduLinkage.</p>

      {/* Seul point d'entrée d'inscription d'une organisation : réservé à ce tableau de bord
          (PlatformDashboard n'est rendu que pour un platform admin, voir dashboard/page.tsx). */}
      <div>
        <Link
          href="/dashboard/organizations/new"
          className="inline-flex rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95"
        >
          + Inscrire une organisation
        </Link>
        {/* PR #19 — ajout d'un établissement à une organisation EXISTANTE (même page, parcours
            « Organisation existante ») : l'organisation n'est jamais recréée. */}
        <Link
          href="/dashboard/organizations/new?mode=existing"
          className="ml-3 inline-flex rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          + Ajouter un établissement
        </Link>
      </div>

      {error && <ErrorRetry message={error} onRetry={load} />}
      {!error && dashboard === null && <p className="text-sm text-slate-400">Chargement des indicateurs...</p>}
      {dashboard && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Organisations" value={String(dashboard.organization_count)} />
          <MetricCard label="Écoles" value={String(dashboard.school_count)} />
          <MetricCard label="Utilisateurs" value={String(dashboard.user_count)} />
          <MetricCard label="Élèves" value={String(dashboard.student_count)} />
          <MetricCard label="Partenaires" value={String(dashboard.partner_count)} />
          <MetricCard label="Inscriptions suivies" value={String(dashboard.enrollment_count)} />
        </div>
      )}
    </div>
  );
}
