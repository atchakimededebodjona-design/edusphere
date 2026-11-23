"use client";

import { ChildCard, ChildrenSkeleton } from "@/components/parent-shell/ChildCard";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { EmptyState, PageHeader } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { parentChildren } from "@/lib/parent/client";

// Pas de nom d'école affiché ici volontairement : GET /schools/{id} exige la permission
// `schools.read` (voir apps/api/app/modules/schools/router.py), qu'un compte PARENT ne reçoit
// jamais (aucune permission RBAC scopée, Phase 7) — l'appeler produirait un 403 systématique.
// Refonte, phase 2 (2026-11-23) : mêmes cartes que l'accueil.
export default function ParentChildrenPage() {
  const { data: children, error, retry } = useAsyncData(parentChildren.list, []);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeader title="Mes enfants" />

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {!error && children === null && <ChildrenSkeleton />}
      {children && children.length === 0 && (
        <EmptyState
          icon="users"
          title="Aucun enfant rattaché"
          description="Aucun enfant n'est encore rattaché à votre compte. Contactez l'administration de l'école de votre enfant pour faire le lien."
        />
      )}

      {children && children.length > 0 && (
        <ul className="flex flex-col gap-3">
          {children.map((child) => (
            <li key={child.id}>
              <ChildCard child={child} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
