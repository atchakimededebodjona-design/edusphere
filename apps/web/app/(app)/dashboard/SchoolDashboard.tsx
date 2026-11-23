"use client";

import Link from "next/link";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ButtonLink } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader, SectionTitle, Skeleton, StatCard } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { cashReports } from "@/lib/cash/client";
import { formatApiAmount, formatMoney, toCents } from "@/lib/fees/allocation";
import { feesSummary } from "@/lib/fees/client";
import { SCHOOL_MENU, allowedMenu, type MenuItem } from "@/lib/navigation/menus";
import { getSchool, getSchoolDashboard } from "@/lib/schools/client";

// Les 4 indicateurs scolaires demandent ces permissions côté API (schools/router.py::get_school_dashboard).
const INDICATOR_PERMISSIONS = ["students.read", "attendance.read", "grades.read", "report_cards.read"];

// Accès rapides : les écrans du quotidien d'abord, filtrés par les droits du compte (mêmes routes et
// mêmes permissions que le menu).
const SHORTCUT_ORDER = [
  "/cashier",
  "/students",
  "/payments",
  "/fees/overdue",
  "/announcements",
  "/report-cards",
  "/attendance",
  "/grades",
  "/cashier/cash-register",
  "/fees",
  "/cashier/supervision",
  "/notifications",
];
const MAX_SHORTCUTS = 6;

function formatRate(rate: number | null): string {
  return rate === null ? "Aucune donnée" : `${rate}%`;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count > 1 ? many : one}`;
}

function StatsSkeleton({ count }: { count: number }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="rounded-xl border border-slate-200 bg-white p-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="mt-2 h-7 w-20" />
        </div>
      ))}
    </div>
  );
}

// Refonte, phase 2 (2026-11-23) — accueil de l'école selon les droits du compte :
// - « Aujourd'hui » (supervision de caisse) : encaissements du jour et caisses ouvertes ;
// - « Finances » (lecture des frais) : attendu, encaissé, reste à payer, frais en retard ;
// - « Scolarité » (les 4 indicateurs historiques) ;
// - accès rapides vers les écrans du compte.
// Chaque bloc n'appelle que des routes existantes, et seulement si le compte en a le droit : jamais de
// « Not enough permissions » à l'arrivée (corrigé en phase 1).
export function SchoolDashboard() {
  const { currentSchoolId, currentSchool, permissions } = useAuth();
  const can = (code: string) => permissions.includes(code);
  const canReadSchool = can("schools.read");
  const canSeeIndicators = INDICATOR_PERMISSIONS.every(can);
  const canSeeFinances = can("fees.read");
  const canSeeToday = can("cash.register.review");
  const schoolId = currentSchoolId ?? "";

  const school = useAsyncData(() => getSchool(schoolId), [schoolId], { enabled: Boolean(currentSchoolId) && canReadSchool });
  const indicators = useAsyncData(() => getSchoolDashboard(schoolId), [schoolId], {
    enabled: Boolean(currentSchoolId) && canSeeIndicators,
  });
  const finances = useAsyncData(() => feesSummary.get(schoolId), [schoolId], {
    enabled: Boolean(currentSchoolId) && canSeeFinances,
  });
  const today = useAsyncData(() => cashReports.daily(schoolId), [schoolId], {
    enabled: Boolean(currentSchoolId) && canSeeToday,
  });

  const schoolName = school.data?.name ?? currentSchool?.name ?? null;
  const currency = today.data?.currency ?? school.data?.currency ?? currentSchool?.currency ?? "";
  const allowed = allowedMenu(SCHOOL_MENU, permissions).flatMap((group) => group.items);
  // Une carte ne mène à un écran que si le menu du compte le propose (mêmes permissions).
  const link = (href: string) => (allowed.some((item) => item.href === href) ? href : undefined);
  const shortcuts = SHORTCUT_ORDER.map((href) => allowed.find((item) => item.href === href))
    .filter((item): item is MenuItem => Boolean(item))
    .slice(0, MAX_SHORTCUTS);

  const collected = today.data?.payments_by_method.reduce(
    (sum, row) => ({
      cents: sum.cents + (toCents(row.completed_total) ?? 0),
      count: sum.count + row.completed_count,
    }),
    { cents: 0, count: 0 },
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Tableau de bord"
        description={
          school.error ? undefined : schoolName ? (
            <>
              Bienvenue sur l&apos;espace de <strong className="text-slate-900">{schoolName}</strong>.
            </>
          ) : (
            "Chargement de l'école..."
          )
        }
        actions={
          canReadSchool ? (
            <ButtonLink href="/school" variant="secondary" icon="settings">
              Paramètres de l&apos;école
            </ButtonLink>
          ) : undefined
        }
      />
      {school.error && <ErrorRetry message={school.error} onRetry={school.retry} />}

      {canSeeToday && (
        <section aria-labelledby="dashboard-today" className="flex flex-col gap-3">
          <SectionTitle id="dashboard-today" title="Aujourd'hui" />
          {today.error && <ErrorRetry message={today.error} onRetry={today.retry} />}
          {!today.data && !today.error && <StatsSkeleton count={2} />}
          {today.data && collected && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                icon="cash"
                tone="success"
                label="Encaissé aujourd'hui"
                value={formatMoney(collected.cents, currency)}
                hint={plural(collected.count, "paiement", "paiements")}
                href={link("/payments")}
                testId="dashboard-collected-today"
              />
              <StatCard
                icon="register"
                label="Caisses ouvertes"
                value={String(today.data.sessions.open_count)}
                hint={plural(today.data.sessions.sessions_count, "caisse ouverte ce jour", "caisses ouvertes ce jour")}
                href={link("/cashier/supervision")}
              />
            </div>
          )}
        </section>
      )}

      {canSeeFinances && (
        <section aria-labelledby="dashboard-finances" className="flex flex-col gap-3">
          <SectionTitle id="dashboard-finances" title="Finances" />
          {finances.error && <ErrorRetry message={finances.error} onRetry={finances.retry} />}
          {!finances.data && !finances.error && <StatsSkeleton count={4} />}
          {finances.data && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard icon="wallet" label="Total attendu" value={formatApiAmount(finances.data.total_due, currency)} href={link("/fees")} />
              <StatCard
                icon="checkSquare"
                tone="success"
                label="Déjà encaissé"
                value={formatApiAmount(finances.data.total_paid, currency)}
                href={link("/payments")}
              />
              <StatCard
                icon="chart"
                tone="warning"
                label="Reste à payer"
                value={formatApiAmount(finances.data.balance, currency)}
                testId="dashboard-balance"
              />
              <StatCard
                icon="clock"
                tone={finances.data.overdue_count > 0 ? "danger" : "success"}
                label="Frais en retard"
                value={String(finances.data.overdue_count)}
                hint={finances.data.overdue_count > 0 ? "Relances à suivre" : "Aucun retard"}
                href={link("/fees/overdue")}
              />
            </div>
          )}
        </section>
      )}

      {canSeeIndicators && (
        <section aria-labelledby="dashboard-school" className="flex flex-col gap-3">
          <SectionTitle id="dashboard-school" title="Scolarité" />
          {indicators.error && <ErrorRetry message={indicators.error} onRetry={indicators.retry} />}
          {!indicators.data && !indicators.error && <StatsSkeleton count={4} />}
          {indicators.data && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard icon="student" label="Élèves actifs" value={String(indicators.data.active_student_count)} href={link("/students")} />
              <StatCard
                icon="clipboard"
                label="Taux de présence"
                value={formatRate(indicators.data.attendance_rate)}
                hint={indicators.data.current_term_name}
                href={link("/attendance")}
              />
              <StatCard
                icon="listChecks"
                label="Complétude des notes"
                value={formatRate(indicators.data.grade_completeness_rate)}
                hint={indicators.data.current_term_name}
                href={link("/grades")}
              />
              <StatCard
                icon="fileText"
                label="Bulletins publiés"
                value={String(indicators.data.published_report_card_count)}
                href={link("/report-cards")}
              />
            </div>
          )}
        </section>
      )}

      {shortcuts.length > 0 && (
        <section aria-labelledby="shortcuts-title" className="flex flex-col gap-3">
          <SectionTitle id="shortcuts-title" title="Accès rapides" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {shortcuts.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex min-h-11 flex-col items-start gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm font-medium text-slate-800 hover:border-primary-300 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
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
    </div>
  );
}
