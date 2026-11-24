"use client";

import { ButtonLink } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { PageHeader, SectionTitle, Skeleton, StatCard } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { PLATFORM_MENU, allowedMenu } from "@/lib/navigation/menus";
import { getPlatformDashboard } from "@/lib/platform/client";

// Refonte, phase 2 (2026-11-23) — accueil de la plateforme : mêmes compteurs, chacun menant à sa liste.
export function PlatformDashboard() {
  const { data, error, retry } = useAsyncData(getPlatformDashboard, []);
  const { permissions } = useAuth();
  const allowed = allowedMenu(PLATFORM_MENU, permissions).flatMap((group) => group.items);
  // Une carte ne mène à une liste que si le menu du compte la propose (mêmes permissions).
  const link = (href: string) => (allowed.some((item) => item.href === href) ? href : undefined);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Administration de la plateforme"
        description="Bienvenue dans l'espace d'administration EduLinkage."
        actions={
          <>
            {/* Seul point d'entrée d'inscription d'une organisation : réservé à ce tableau de bord
                (PlatformDashboard n'est rendu que pour un platform admin, voir dashboard/page.tsx). */}
            <ButtonLink href="/dashboard/organizations/new">+ Inscrire une organisation</ButtonLink>
            {/* PR #19 — ajout d'un établissement à une organisation EXISTANTE (même page, parcours
                « Organisation existante ») : l'organisation n'est jamais recréée. */}
            <ButtonLink href="/dashboard/organizations/new?mode=existing" variant="secondary">
              + Ajouter un établissement
            </ButtonLink>
          </>
        }
      />

      <section aria-labelledby="platform-figures" className="flex flex-col gap-3">
        <SectionTitle id="platform-figures" title="En chiffres" />
        {error && <ErrorRetry message={error} onRetry={retry} />}
        {!data && !error && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
            {Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="rounded-xl border border-slate-200 bg-white p-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="mt-2 h-7 w-16" />
              </div>
            ))}
          </div>
        )}
        {data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard icon="building" label="Organisations" value={String(data.organization_count)} href={link("/platform/organizations")} />
            <StatCard icon="school" label="Écoles" value={String(data.school_count)} href={link("/platform/schools")} />
            <StatCard icon="users" label="Utilisateurs" value={String(data.user_count)} href={link("/platform/accounts")} />
            <StatCard icon="student" label="Élèves" value={String(data.student_count)} />
            <StatCard icon="link" label="Partenaires" value={String(data.partner_count)} href={link("/platform/partners")} />
            <StatCard icon="listChecks" label="Inscriptions suivies" value={String(data.enrollment_count)} />
          </div>
        )}
      </section>
    </div>
  );
}
