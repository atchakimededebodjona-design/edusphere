"use client";

import { useCallback, useEffect, useState } from "react";
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

      {error && <ErrorRetry message={error} onRetry={load} />}
      {!error && dashboard === null && <p className="text-sm text-slate-400">Chargement des indicateurs...</p>}
      {dashboard && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Organisations" value={String(dashboard.organization_count)} />
          <MetricCard label="Écoles" value={String(dashboard.school_count)} />
          <MetricCard label="Utilisateurs" value={String(dashboard.user_count)} />
          <MetricCard label="Élèves" value={String(dashboard.student_count)} />
        </div>
      )}
    </div>
  );
}
