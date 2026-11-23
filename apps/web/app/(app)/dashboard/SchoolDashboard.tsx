"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Icon } from "@/components/ui/Icon";
import { ApiError } from "@/lib/api/client";
import { getSchool, getSchoolDashboard, type School, type SchoolDashboard as SchoolDashboardData } from "@/lib/schools/client";
import { useAuth } from "@/lib/auth/useAuth";
import { SCHOOL_MENU, allowedMenu } from "@/lib/navigation/menus";

// Les 4 indicateurs demandent ces permissions côté API (schools/router.py::get_school_dashboard).
const INDICATOR_PERMISSIONS = ["students.read", "attendance.read", "grades.read", "report_cards.read"];

function MetricCard({ label, value, period }: { label: string; value: string; period?: string | null }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-600">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold tabular-nums text-slate-900">{value}</p>
      {period && <p className="mt-1 text-xs text-slate-600">{period}</p>}
    </div>
  );
}

function formatRate(rate: number | null): string {
  return rate === null ? "Aucune donnée" : `${rate}%`;
}

// Refonte, phase 1 (2026-11-23) : le tableau de bord ne demande plus que ce que le compte a le droit de
// voir. Avant, un comptable ou un caissier y voyait « Not enough permissions » ; sans les indicateurs, il
// trouve maintenant des accès rapides vers ses propres écrans.
export function SchoolDashboard() {
  const { currentSchoolId, currentSchool, permissions } = useAuth();
  const canReadSchool = permissions.includes("schools.read");
  const canSeeIndicators = INDICATOR_PERMISSIONS.every((code) => permissions.includes(code));
  const [school, setSchool] = useState<School | null>(null);
  const [schoolError, setSchoolError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<SchoolDashboardData | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const loadSchool = useCallback(() => {
    if (!currentSchoolId || !canReadSchool) return;
    setSchoolError(null);
    getSchool(currentSchoolId)
      .then(setSchool)
      .catch((err) => setSchoolError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [currentSchoolId, canReadSchool]);

  useEffect(() => {
    loadSchool();
  }, [loadSchool]);

  const loadDashboard = useCallback(() => {
    if (!currentSchoolId || !canSeeIndicators) return;
    setDashboard(null);
    setDashboardError(null);
    getSchoolDashboard(currentSchoolId)
      .then(setDashboard)
      .catch((err) => setDashboardError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [currentSchoolId, canSeeIndicators]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const schoolName = school?.name ?? currentSchool?.name ?? null;
  const shortcuts = allowedMenu(SCHOOL_MENU, permissions)
    .flatMap((group) => group.items)
    .filter((item) => item.href !== "/dashboard");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Tableau de bord</h1>
      {schoolError ? (
        <ErrorRetry message={schoolError} onRetry={loadSchool} />
      ) : schoolName ? (
        <p className="text-slate-600">
          Bienvenue sur l&apos;espace de <strong>{schoolName}</strong>.
        </p>
      ) : (
        <p className="text-slate-600">Chargement de l&apos;école...</p>
      )}

      {canSeeIndicators && (
        <>
          {dashboardError && <ErrorRetry message={dashboardError} onRetry={loadDashboard} />}
          {!dashboardError && dashboard === null && <p className="text-sm text-slate-600">Chargement des indicateurs...</p>}
          {dashboard && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Élèves actifs" value={String(dashboard.active_student_count)} />
              <MetricCard label="Taux de présence" value={formatRate(dashboard.attendance_rate)} period={dashboard.current_term_name} />
              <MetricCard
                label="Complétude des notes"
                value={formatRate(dashboard.grade_completeness_rate)}
                period={dashboard.current_term_name}
              />
              <MetricCard label="Bulletins publiés" value={String(dashboard.published_report_card_count)} />
            </div>
          )}
        </>
      )}

      {!canSeeIndicators && shortcuts.length > 0 && (
        <section aria-labelledby="shortcuts-title" className="flex flex-col gap-3">
          <h2 id="shortcuts-title" className="text-lg font-bold text-slate-900">
            Accès rapides
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {shortcuts.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm font-medium text-slate-800 hover:border-primary-300 hover:bg-primary-50"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
                  <Icon name={item.icon} />
                </span>
                {item.label}
              </Link>
            ))}
          </div>
        </section>
      )}

      {canReadSchool && (
        <Link href="/school" className="w-fit rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700">
          Paramètres de l&apos;école
        </Link>
      )}
    </div>
  );
}
