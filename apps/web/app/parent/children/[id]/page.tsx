"use client";

import { useId, useState } from "react";
import { useParams } from "next/navigation";
import { ChildInitials } from "@/components/parent-shell/ChildCard";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { EmptyState, Skeleton } from "@/components/ui/Surface";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { parentChildren } from "@/lib/parent/client";
import { ChildAttendance } from "@/app/parent/children/[id]/ChildAttendance";
import { ChildGrades } from "@/app/parent/children/[id]/ChildGrades";
import { ChildReportCards } from "@/app/parent/children/[id]/ChildReportCards";
import { ChildFees } from "@/app/parent/children/[id]/ChildFees";

type TabKey = "attendance" | "grades" | "report-cards" | "fees";

const TABS: { key: TabKey; label: string }[] = [
  { key: "attendance", label: "Présence" },
  { key: "grades", label: "Notes" },
  { key: "report-cards", label: "Bulletins" },
  { key: "fees", label: "Frais" },
];

// Sécurité : la liste `/parent/children` est déjà scopée côté serveur à l'utilisateur courant
// (voir apps/api/app/modules/parent/service.py::list_children). Trouver l'enfant par id dans
// cette liste n'est qu'une commodité d'affichage (nom, matricule) — ce n'est JAMAIS ce qui protège
// les données : chaque onglet ci-dessous refait son propre appel `/parent/children/{id}/...`, qui
// revalide indépendamment côté serveur que cet élève est bien un enfant de l'utilisateur courant
// (`_get_child_or_404`). Un id dans l'URL n'est donc jamais une preuve d'autorisation à lui seul.
//
// Refonte, phase 2 (2026-11-23) : en-tête de l'enfant, vrais onglets accessibles (défilants sur
// téléphone), mêmes appels qu'avant.
export default function ChildDetailPage() {
  const params = useParams<{ id: string }>();
  const studentId = params.id;
  const tabsId = useId();
  const [tab, setTab] = useState<TabKey>("attendance");
  const { data: children, error, retry } = useAsyncData(parentChildren.list, []);

  if (error) return <ErrorRetry message={error} onRetry={retry} />;
  if (children === null) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Chargement">
        <div className="flex items-center gap-3">
          <Skeleton className="h-14 w-14 rounded-full" />
          <div>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="mt-2 h-4 w-32" />
          </div>
        </div>
        <Skeleton className="h-11 w-full" />
      </div>
    );
  }

  const child = children.find((c) => c.id === studentId);
  if (!child) {
    return (
      <EmptyState
        icon="user"
        title="Fiche introuvable"
        description="Cet élève n'est pas rattaché à votre compte, ou n'existe pas."
        action={
          <ButtonLink href="/parent/children" variant="secondary">
            Mes enfants
          </ButtonLink>
        }
      />
    );
  }

  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <div className="flex items-center gap-3">
        <ChildInitials child={child} size="lg" />
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-slate-900">
            {child.first_name} {child.last_name}
          </h1>
          <p className="text-sm text-slate-600">Matricule {child.matricule}</p>
        </div>
      </div>

      <div>
        <Tabs id={tabsId} label={`Suivi de ${child.first_name}`} tabs={TABS} value={tab} onChange={setTab} />
        <TabPanel id={tabsId} active={tab}>
          {tab === "attendance" && <ChildAttendance studentId={child.id} />}
          {tab === "grades" && <ChildGrades studentId={child.id} />}
          {tab === "report-cards" && (
            <ChildReportCards studentId={child.id} studentLabel={`${child.first_name}_${child.last_name}`} />
          )}
          {tab === "fees" && <ChildFees studentId={child.id} />}
        </TabPanel>
      </div>
    </div>
  );
}
