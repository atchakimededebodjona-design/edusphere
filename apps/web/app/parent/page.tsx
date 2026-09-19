"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { parentChildren } from "@/lib/parent/client";
import type { Student } from "@/lib/students/client";

export default function ParentDashboardPage() {
  const { user } = useAuth();
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
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">
        Bonjour{user ? `, ${user.full_name}` : ""}
      </h1>

      {error && <ErrorRetry message={error} onRetry={load} />}
      {!error && children === null && <p className="text-sm text-slate-500">Chargement...</p>}

      {children && children.length === 0 && (
        <p className="max-w-md text-sm text-slate-600">
          Aucun enfant n&apos;est encore rattaché à votre compte. Contactez l&apos;administration de
          l&apos;école de votre enfant pour faire le lien.
        </p>
      )}

      {children && children.length > 0 && (
        <>
          <p className="text-slate-600">
            {children.length === 1
              ? "1 enfant est rattaché à votre compte."
              : `${children.length} enfants sont rattachés à votre compte.`}
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {children.map((child) => (
              <Link
                key={child.id}
                href={`/parent/children/${child.id}`}
                className="rounded border border-slate-200 bg-white p-4 hover:border-slate-400"
              >
                <p className="font-semibold text-slate-900">
                  {child.first_name} {child.last_name}
                </p>
                <p className="text-sm text-slate-500">Matricule {child.matricule}</p>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
