"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getSchool, getSchoolDashboard, type School, type SchoolDashboard } from "@/lib/schools/client";
import { useAuth } from "@/lib/auth/useAuth";

function MetricCard({ label, value, period }: { label: string; value: string; period?: string | null }) {
  return (
    <div className="rounded border border-slate-200 p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
      {period && <p className="mt-1 text-xs text-slate-400">{period}</p>}
    </div>
  );
}

function formatRate(rate: number | null): string {
  return rate === null ? "Aucune donnée" : `${rate}%`;
}

export default function DashboardPage() {
  const { currentSchoolId, permissions } = useAuth();
  const [school, setSchool] = useState<School | null>(null);
  const [dashboard, setDashboard] = useState<SchoolDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  useEffect(() => {
    if (currentSchoolId) {
      void getSchool(currentSchoolId).then(setSchool);
    }
  }, [currentSchoolId]);

  useEffect(() => {
    if (!currentSchoolId) return;
    setDashboard(null);
    setDashboardError(null);
    getSchoolDashboard(currentSchoolId)
      .then(setDashboard)
      .catch((err) => setDashboardError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [currentSchoolId]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Tableau de bord</h1>
      {school ? (
        <p className="text-slate-600">
          Bienvenue sur l&apos;espace de <strong>{school.name}</strong>.
        </p>
      ) : (
        <p className="text-slate-500">Chargement de l&apos;école...</p>
      )}

      {dashboardError && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {dashboardError}
        </p>
      )}
      {!dashboardError && dashboard === null && (
        <p className="text-sm text-slate-400">Chargement des indicateurs...</p>
      )}
      {dashboard && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Élèves actifs" value={String(dashboard.active_student_count)} />
          <MetricCard
            label="Taux de présence"
            value={formatRate(dashboard.attendance_rate)}
            period={dashboard.current_term_name}
          />
          <MetricCard
            label="Complétude des notes"
            value={formatRate(dashboard.grade_completeness_rate)}
            period={dashboard.current_term_name}
          />
          <MetricCard label="Bulletins publiés" value={String(dashboard.published_report_card_count)} />
        </div>
      )}

      {permissions.includes("schools.read") && (
        <Link href="/school" className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white">
          Paramètres de l&apos;école
        </Link>
      )}
    </div>
  );
}
