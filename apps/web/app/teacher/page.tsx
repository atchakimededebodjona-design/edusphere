"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Badge, Card, PageHeader, SectionTitle, Skeleton, StatCard } from "@/components/ui/Surface";
import { formatDateFR } from "@/lib/format/date";
import { describeTeacherError, teacherApi, type TeacherDashboard } from "@/lib/teacher/client";

/** Grande action du quotidien, pensée pour le pouce. */
function MainAction({ href, icon, title, text }: { href: string; icon: IconName; title: string; text: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-4 rounded-xl bg-primary-600 p-4 text-white shadow-sm transition-colors hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
    >
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-white/15">
        <Icon name={icon} className="h-6 w-6" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-lg font-bold">{title}</span>
        <span className="block text-sm text-primary-50">{text}</span>
      </span>
      <Icon name="chevronRight" className="h-5 w-5 shrink-0" />
    </Link>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Chargement du tableau de bord">
      <Skeleton className="h-8 w-56" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-24 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

// Refonte, phase 2 (2026-11-23) — accueil enseignant : l'appel et les notes d'abord (grandes actions),
// puis les chiffres et les dernières évaluations et notifications. Mêmes données qu'avant
// (GET /teacher/dashboard).
export default function TeacherDashboardPage() {
  const [data, setData] = useState<TeacherDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    teacherApi.dashboard().then(setData).catch((err) => setError(describeTeacherError(err)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!data) return <DashboardSkeleton />;

  const unread = data.recent_notifications.filter((n) => !n.read).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`Bonjour ${data.teacher_name}`}
        description={data.schools.length > 0 ? data.schools.map((s) => s.name).join(", ") : "Aucune école rattachée"}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <MainAction href="/teacher/attendance" icon="clipboard" title="Faire l'appel" text="Présents, absents et retards du jour" />
        <MainAction href="/teacher/grades" icon="listChecks" title="Saisir les notes" text="Évaluations et notes de vos classes" />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard icon="layers" label="Classes affectées" value={String(data.class_count)} href="/teacher/classes" />
        <StatCard icon="board" label="Matières affectées" value={String(data.subject_count)} />
        <StatCard icon="student" label="Élèves suivis" value={String(data.student_count)} href="/teacher/students" />
        <StatCard
          icon="bell"
          label="Notifications récentes"
          value={String(data.recent_notifications.length)}
          hint={unread > 0 ? `${unread} non lue${unread > 1 ? "s" : ""}` : undefined}
          href="/teacher/notifications"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-3">
          <SectionTitle
            title="Évaluations récentes"
            action={
              <ButtonLink href="/teacher/classes" variant="ghost" size="sm">
                Mes classes
              </ButtonLink>
            }
          />
          {data.recent_assessments.length === 0 ? (
            <p className="text-sm text-slate-600">Aucune évaluation pour le moment.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-slate-100 text-sm">
              {data.recent_assessments.map((a) => (
                <li key={a.id} className="flex items-start justify-between gap-3 py-2">
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{a.name}</span>
                    <span className="block text-xs text-slate-600">
                      {a.class_name} · {a.subject_name}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-600">{formatDateFR(a.assessment_date)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col gap-3">
          <SectionTitle
            title="Notifications récentes"
            action={
              <ButtonLink href="/teacher/notifications" variant="ghost" size="sm">
                Tout voir
              </ButtonLink>
            }
          />
          {data.recent_notifications.length === 0 ? (
            <p className="text-sm text-slate-600">Aucune notification.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-slate-100 text-sm">
              {data.recent_notifications.map((n) => (
                <li key={n.id} className="flex items-start justify-between gap-3 py-2">
                  <span className={n.read ? "text-slate-600" : "font-medium text-slate-900"}>{n.title}</span>
                  {!n.read && <Badge tone="info">Nouveau</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
