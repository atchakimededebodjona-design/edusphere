"use client";

import { ChildCard, ChildrenSkeleton } from "@/components/parent-shell/ChildCard";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { EmptyState, PageHeader } from "@/components/ui/Surface";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { parentChildren } from "@/lib/parent/client";

const NO_CHILD =
  "Aucun enfant n'est encore rattaché à votre compte. Contactez l'administration de l'école de votre enfant pour faire le lien.";

// Refonte, phase 2 (2026-11-23) — accueil parent : une carte par enfant, qui mène à sa fiche (notes,
// présences, frais, bulletins). Mêmes données qu'avant (GET /parent/children).
export default function ParentDashboardPage() {
  const { user } = useAuth();
  const { data: children, error, retry } = useAsyncData(parentChildren.list, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`Bonjour${user ? `, ${user.full_name}` : ""}`}
        description={
          children && children.length > 0
            ? children.length === 1
              ? "1 enfant est rattaché à votre compte."
              : `${children.length} enfants sont rattachés à votre compte.`
            : undefined
        }
      />

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {!error && children === null && <ChildrenSkeleton />}

      {children && children.length === 0 && <EmptyState icon="users" title="Aucun enfant rattaché" description={NO_CHILD} />}

      {children && children.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {children.map((child) => (
            <ChildCard key={child.id} child={child} />
          ))}
        </div>
      )}
    </div>
  );
}
