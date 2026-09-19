"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { parentChildren } from "@/lib/parent/client";
import type { Student } from "@/lib/students/client";

// Pas de nom d'école affiché ici volontairement : GET /schools/{id} exige la permission
// `schools.read` (voir apps/api/app/modules/schools/router.py), qu'un compte PARENT ne reçoit
// jamais (aucune permission RBAC scopée, Phase 7) — l'appeler produirait un 403 systématique.
export default function ParentChildrenPage() {
  const [children, setChildren] = useState<Student[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    parentChildren
      .list()
      .then(setChildren)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Mes enfants</h1>

      {error && <ErrorRetry message={error} onRetry={load} />}
      {!error && children === null && <p className="text-sm text-slate-500">Chargement...</p>}
      {children && children.length === 0 && (
        <p className="text-sm text-slate-600">
          Aucun enfant n&apos;est encore rattaché à votre compte. Contactez l&apos;administration de
          l&apos;école de votre enfant pour faire le lien.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {children?.map((child) => (
          <li key={child.id}>
            <Link
              href={`/parent/children/${child.id}`}
              className="flex items-center justify-between rounded border border-slate-200 bg-white px-4 py-3 text-sm hover:border-slate-400"
            >
              <span className="font-medium text-slate-900">
                {child.first_name} {child.last_name}
              </span>
              <span className="text-slate-500">Matricule {child.matricule}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
